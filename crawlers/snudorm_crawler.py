import asyncio
import datetime
import re

from bs4 import BeautifulSoup
from pytz import timezone

from crawlers.base_crawler import (
    AddRestaurantDetail,
    FindParenthesisHash,
    FindPrice,
    Meal,
    RemoveInfoFromMealName,
    RemoveMealIdentifierFromMealName,
    RestaurantCrawler,
    text_normalizer,
)


class SnudormRestaurantCrawler(RestaurantCrawler):
    url = "https://snudorm.snu.ac.kr/foodmenu/"
    restaurant = "기숙사식당"
    normalizer_classes = [
        FindPrice,
        FindParenthesisHash,
        AddRestaurantDetail,
        RemoveInfoFromMealName,
        RemoveMealIdentifierFromMealName,
    ]

    next_line_str = [
        "봄",
        "소반",
        "콤비메뉴",
        "셀프코너",
        "채식뷔페",
        "추가코너",
        "돈까스비빔면셋트",
        "탄탄비빔면셋트",
    ]
    next_line_keyword = []  # 다음 한 줄 있는 것들
    multi_line_keywords = {}  # 다음에 여러줄 있는 것들
    multi_line_finisher = (
        {}
    )  # multiline이 끝나는 지표. ex. 로직상 주문식 메뉴까지 append된 뒤에 확인한다. 따라서 마지막에 주문식 메뉴 따로 빼줘야함
    multi_line_finisher_pair = {}

    restaurant_phone_dict = {}
    restaurant_adapter = {"생협기숙사(919동)": "919동", "아워홈(901동)": "아워홈"}

    except_restaurant_list = []  # snudorm에서 처리

    def __init__(self):
        super().__init__()

    def is_next_line_keyword(self, meal):
        if not meal:
            return False
        code = text_normalizer(meal.name, True)
        return any((str == code) for str in self.next_line_str) or any((str in code) for str in self.next_line_keyword)

    def filter_menu_names(self, meal_names: list):
        return [name for name in meal_names if self.is_meal_name_when_normalized(name)]

    def filter_and_split_menu_names(self, meal_name: list):
        names = []
        for name in meal_name:
            if name == "" or name == "\xa0":
                continue
            splitted = re.split(r"(3층 교직원|\d+\s*원)", name)
            if len(splitted) == 1:
                names.append(name)
            else:
                for i, v in enumerate(splitted):
                    if re.match(r"\d+\s*원", v):
                        if i - 1 >= 0:
                            splitted[i - 1] += v
                        splitted[i] = ""
                names += [v for v in splitted if v != ""]
        return names

    def get_multi_line_delimiter(self, meal):
        if not meal:
            return None
        code = text_normalizer(meal.name, True)
        for (
            keyword,
            finisher,
        ) in self.multi_line_finisher.items():  # finisher 발견되면 delimiter가 없는 것 취급
            if keyword in code and finisher in code:
                return None
        for delimiter, keywords in self.multi_line_keywords.items():
            if any((str in code) for str in keywords):
                return delimiter
        return None

    def combine(self, last_meal, meal, delimiter=": "):
        if not last_meal:
            return meal
        if not meal:
            return last_meal
        last_meal.set_name(last_meal.name + delimiter + meal.name)
        if not last_meal.price:
            last_meal.set_price(meal.price)
        return last_meal

    async def run_7days(self):
        date = datetime.datetime.now(timezone("Asia/Seoul")).date()
        tasks = [self.run(date=date + datetime.timedelta(days=i)) for i in range(7)]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, date=None, **kwargs):
        if not date:
            date = datetime.datetime.now(timezone("Asia/Seoul")).date()
        url = self.url + f"?date={date.year}-{date.month:02d}-{date.day:02d}"
        await super().run(url, date=date, **kwargs)

    def found_meal(self, meal):
        if meal and self.is_meal_name_when_normalized(meal.name):
            self.meals.append(meal)

    def get_name_from_raw_restaurant(self, raw_restaurant):
        normalized = text_normalizer(raw_restaurant)

        # 기존 기숙사 식당 이름과 매칭되도록 함
        # 24.11.11 기준 생협기숙사(919동), 아워홈(901동)만 존재
        # 24.11.10 기준 기숙사식당>919동, 기숙사식당>아워홈으로 되어있음
        full_restaurant_anme = self.restaurant + ">" + self.restaurant_adapter.get(normalized)
        return full_restaurant_anme

    def crawl(self, soup: BeautifulSoup, **kwargs):
        date = kwargs.get("date", datetime.datetime.now(timezone("Asia/Seoul")).date())
        table = soup.find("table", {"class": "menu-table"})
        if not table:
            return
        trs = table.tbody.find_all("tr", recursive=False)

        for tr in trs:
            tds = tr.find_all("td", recursive=False)

            raw_restaurant = tds[0].text
            restaurant = self.get_name_from_raw_restaurant(raw_restaurant)
            if restaurant in self.except_restaurant_list:
                continue

            for col_idx, td in enumerate(tds[1:]):
                # meal type이 더 이상 ths에 포함되지 않고 tds 내부로 이동.
                meal_type = td["class"][0]

                # td.text에서 식단을 한번에 가져오는 것으로 변경
                names = td.text.split("\n")

                last_meal = None
                next_line_merged = False
                filtered_names = []
                filtered_names = self.filter_menu_names(names)

                for name in filtered_names:
                    meal = Meal(restaurant, name, date, meal_type)
                    meal = self.normalize(meal)

                    if self.is_meal_name_when_normalized(meal.name):
                        # ISSUE#54 220동 이름 오류 수정
                        # ex) ㅁ 바비든든( ~ ): 덮밥류 -> 바비든든: 덮밥류

                        name_cleaned = meal.name
                        for to_clean in ["ㅁ ", "( ~ )", "(~)"]:
                            name_cleaned = name_cleaned.replace(to_clean, "")
                        meal.set_name(name_cleaned)

                        # 다음 한줄만 추가하는 경우
                        if not next_line_merged and self.is_next_line_keyword(last_meal):
                            last_meal = self.combine(last_meal, meal)
                            next_line_merged = True

                        else:
                            delimiter = self.get_multi_line_delimiter(last_meal)
                            # delimiter에 해당하는 경우에는 여기 걸림
                            if delimiter is not None:
                                last_meal = self.combine(last_meal, meal, delimiter)
                            # 그래서 여기서 combine 된다.
                            else:  # delimit 하지 않는 경우는
                                for finisher_to_remove in self.multi_line_finisher_pair.values():
                                    if finisher_to_remove in str(last_meal):
                                        finisher_removed_name = last_meal.name.replace(finisher_to_remove, "")
                                        if finisher_removed_name.endswith("+"):
                                            finisher_removed_name = finisher_removed_name[:-1]
                                        last_meal.set_name(finisher_removed_name)
                                self.found_meal(last_meal)
                                last_meal = meal  # 그거 자체로 메뉴다.
                            next_line_merged = False
                    elif self.get_multi_line_delimiter(last_meal) is None:
                        if meal.restaurant != restaurant:
                            meal = Meal(raw_restaurant, name, date, meal_type)
                            meal = self.normalize(meal)
                            restaurant = meal.restaurant
                        self.found_meal(last_meal)
                        last_meal = None
                        next_line_merged = False
                if last_meal:
                    self.found_meal(last_meal)
