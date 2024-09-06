import datetime
import json
import re
from abc import ABCMeta, abstractmethod

import aiohttp
import urllib3
from bs4 import BeautifulSoup
from pytz import timezone


def text_normalizer(text, only_letters=False):
    non_letters = [
        r"\s",
        "<",
        ">",
        r"\(",
        r"\)",
        r"\[",
        r"\]",
        ",",
        r"\*",
        "&",
        r"\+",
        "-",
        r"/",
        ":",
        "#",
        r"\.",
        "♣",
        "▷",
        "ㅁ",
        "~",
    ]
    text = re.sub(r"\n|\(\)|<>", "", text).strip().strip(":")
    text = re.sub(r"\xa0", " ", text)
    if only_letters:
        text = re.sub("|".join(non_letters), "", text)
    return text


class Meal:
    BR = "BR"
    LU = "LU"
    DN = "DN"
    type_handler = {
        BR: BR,
        LU: LU,
        DN: DN,
        "아침": BR,
        "점심": LU,
        "저녁": DN,
        "중식": LU,
        "석식": DN,
        "breakfast": BR,
        "lunch": LU,
        "dinner": DN,
    }

    def __init__(self, restaurant="", name="", date=None, type="", price=None, etc=None):
        self.set_restaurant(restaurant)
        self.set_name(name)
        self.set_date(date)
        self.set_type(type)
        self.set_price(price)
        self.set_etc(etc)

    def set_restaurant(self, restaurant):
        self.restaurant = text_normalizer(restaurant)

    def set_name(self, name):
        self.name = text_normalizer(name)

    def set_date(self, date=None):
        if not date:
            now = datetime.datetime.now(timezone("Asia/Seoul"))
            date = datetime.date.fromtimestamp(now.timestamp())
        if isinstance(date, datetime.date):
            self.date = date
        else:
            year = datetime.datetime.now(timezone("Asia/Seoul")).year
            nums = re.findall(r"\d{1,2}", date)
            month = int(nums[0])
            day = int(nums[1])
            self.date = datetime.date(year, month, day)

    def set_type(self, type):
        self.type = self.type_handler.get(text_normalizer(type, True))

    def set_price(self, price):
        if isinstance(price, int):
            self.price = price
        else:
            if not price:
                self.price = None
            else:
                self.price = int(re.sub(r"\D", "", price))

    def set_etc(self, etc):
        self.etc = etc if etc else []

    def __str__(self):
        return f"{self.type}> {self.name} | {self.restaurant} | {self.date.isoformat()} | {self.price} | {repr(', '.join(self.etc))}"

    def as_dict(self):
        return dict(
            restaurant=self.restaurant,
            name=self.name,
            date=self.date,
            type=self.type,
            price=self.price,
            etc=json.dumps(self.etc),
        )


class MealNormalizer(metaclass=ABCMeta):
    @abstractmethod
    def normalize(self, meal, **kwargs):
        pass


class FindPrice(MealNormalizer):
    def normalize(self, meal, **kwargs):
        p = re.compile(r"([1-9]\d{0,2}[,.]?\d00)(.*?원)?")
        m = p.search(meal.name)
        if m:
            meal.set_price(m.group(1))
            meal.set_name(p.sub("", meal.name))
        return meal


class FindParenthesisHash(MealNormalizer):
    def normalize(self, meal, **kwargs):
        # 학생회관 no-meat 메뉴 마크: (#), [#]
        if "(#)" in meal.name or "[#]" in meal.name or "< 채식뷔페 >:" in meal.name:
            meal.set_name(meal.name.replace("(#)", "").replace("[#]", ""))
            meal.etc.append("No meat")
        return meal


class RestaurantCrawler(metaclass=ABCMeta):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0"}
    url = ""
    normalizer_classes = []
    not_meal = [
        "휴무",
        "휴점",
        "폐점",
        "휴업",
        "제공",
        "운영",
        "won",
        "한달간",
        "구독서비스",
        r"월\d*회",
        "일반식코너",
        "휴관",
        "요일별",
        "문의",
        "점심",
        "저녁",
        "배식시간",
        "평일",
        "토요일",
        "TakeOut",
        "셋트메뉴",
        "단품메뉴",
        "사이드메뉴",
        "결제",
        "혼잡시간",
        "말렌카케이크",
        "1조각홀케이크",
        "식사",
        "사이드",
        "오전",
        "오후",
        "브레이크",  # 라운지오 (오후 2시 40~오후 4시 브레이크 타임)
        "TAKE",  # 301동 <TAKE-OUT: 9시~16시> 및 ★TAKE-OUT 카페 301동
        "대학원생",  # 301동 12:30~14:00(학생,대학원생 이용)
        "준비수량",  # 301동 '08:20~준비수량소진시 까지,'
        "학기중",  # 301동 '*학기중  일 200식 한정*'
        "2중선택",  # 301동 (1),(2)중 선택 1, (1), (2)중 선택 1
    ]

    def __init__(self):
        self.meals = []

    @abstractmethod
    async def run_30days(self):
        pass

    async def run(self, url=None, **kwargs):
        urllib3.disable_warnings()
        if url is None:
            url = self.url
        try:
            async with aiohttp.ClientSession(
                headers=self.headers,
                connector=aiohttp.TCPConnector(ssl=False),
            ) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        print(f"Failed to fetch {url}: Status code {response.status}")
                        return
                    html = await response.read()
                    # html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    self.crawl(soup, **kwargs)
        except Exception as e:
            print(f"Error in Run: {str(e)}")
            print(f"URL: {url}")

    def normalize(self, meal, **kwargs):
        for normalizer_cls in self.normalizer_classes:
            meal = normalizer_cls().normalize(meal, **kwargs)
        return meal

    def is_meal_name_when_normalized(self, name):
        normalized_name = text_normalizer(name, True)
        if not normalized_name or normalized_name == "메뉴":
            return False
        is_meal_name = all(re.match(".*" + p + ".*", normalized_name) is None for p in self.not_meal)
        return is_meal_name

    def found_meal(self, meal):
        if meal and self.is_meal_name_when_normalized(meal.name):
            self.meals.append(meal)

    @abstractmethod
    def crawl(self, soup, **kwargs):
        pass


def print_meals(meals):
    print("[")
    for meal in meals:
        print("\t" + str(meal))
    print("]")
    print("total #:", len(meals))
