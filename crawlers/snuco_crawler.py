import asyncio
import datetime
import re

from pytz import timezone

from crawlers.base_crawler import (
    FindParenthesisHash,
    FindPrice,
    Meal,
    MealNormalizer,
    RestaurantCrawler,
    text_normalizer,
)


class RemoveMealNumber(MealNormalizer):
    def normalize(self, meal, **kwargs):
        if "①" in meal.name or "②" in meal.name:
            meal.set_name(meal.name.replace("①", ""))
            meal.set_name(meal.name.replace("②", ""))
        return meal


class RemoveInfoFromMealName(MealNormalizer):
    info_sign = ["※", "►", "※", "브레이크 타임"]

    def normalize(self, meal, **kwargs):
        meal.set_name(re.sub("(" + "|".join(self.info_sign) + ").*", "", meal.name))
        return meal


class FindRestaurantDetail(MealNormalizer):
    restaurant_regex = [
        r"(.*)\( ?(\d층.*)\)(.*)",
        r"(.*)\((.*식당) ?\)(.*)",
        r"(.*)< ?(\d층.*)>(.*)",
        r"(.*)<(.*식당) ?>(.*)",
        r"(.*)<(테이크아웃)>(.*)",
    ]

    def normalize(self, meal, **kwargs):
        for regex in self.restaurant_regex:
            m = re.match(regex, meal.name)
            if m:
                meal.set_restaurant(meal.restaurant + ">" + m.group(2).strip())
                meal.set_name(m.group(1).strip() + m.group(3).strip())
        return meal


class SnucoRestaurantCrawler(RestaurantCrawler):
    url = "https://snuco.snu.ac.kr/foodmenu/"
    normalizer_classes = [
        FindPrice,
        FindParenthesisHash,
        FindRestaurantDetail,
        RemoveInfoFromMealName,
        RemoveMealNumber,
    ]
    next_line_str = ["봄", "소반", "콤비메뉴", "셀프코너", "채식뷔페", "추가코너", "돈까스비빔면셋트", "탄탄비빔면셋트"]
    next_line_keyword = ["지역맛집따라잡기", "호구셋트"]  # 다음 한 줄 있는 것들
    multi_line_keywords = {"+": ["셀프코너", "채식뷔페", "뷔페"], " / ": ["추가코너"]}  # 다음에 여러줄 있는 것들
    multi_line_finisher = {
        "셀프코너": "주문식메뉴"
    }  # multiline이 끝나는 지표. ex. 로직상 주문식 메뉴까지 append된 뒤에 확인한다. 따라서 마지막에 주문식 메뉴 따로 빼줘야함
    multi_line_finisher_pair = {"주문식메뉴": "<주문식 메뉴>"}

    restaurant_phone_dict = {
        "8819072": "기숙사식당",
        "8805543": "학생회관식당",
        "8807888": "자하연식당>2층",
        "8807889": "자하연식당>3층",
        "8761006": "예술계식당",
        "8827005": "라운지오",
        "8809358": "두레미담",
        "8808697": "동원관식당",
        "8898956": "공대간이식당",
        "8805545": "3식당",
        "8801939": "302동식당",
        "8898955": "301동식당",
        "8871123": "220동식당",
    }
    except_restaurant_list = ["기숙사식당"]  # snudorm에서 처리

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
        for keyword, finisher in self.multi_line_finisher.items():  # finisher 발견되면 delimiter가 없는 것 취급
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

    async def run_30days(self):
        date = datetime.datetime.now(timezone("Asia/Seoul")).date()
        tasks = [self.run(date=date + datetime.timedelta(days=i)) for i in range(30)]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, date=None, **kwargs):
        if not date:
            date = datetime.datetime.now(timezone("Asia/Seoul")).date()
        url = self.url + f"?date={date.year}-{date.month:02d}-{date.day:02d}"
        await super().run(url, date=date, **kwargs)

    def found_meal(self, meal):
        if meal and self.is_meal_name_when_normalized(meal.name) and "교직" not in meal.name:
            self.meals.append(meal)

    def get_name_from_raw_restaurant(self, row_restaurant):
        normalized = text_normalizer(row_restaurant)
        phone_match = re.match(r".*\((\d+-\d+)\)", normalized)

        if phone_match is None:
            return normalized

        phone = phone_match.group(1).replace("-", "").strip()

        restaurant_name = self.restaurant_phone_dict[phone]
        if restaurant_name is None:
            print(f"New phone detected: {phone}")
            return normalized
        else:
            return restaurant_name

    def crawl(self, soup, **kwargs):
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
                if "자하연식당" in restaurant:
                    filtered_names = self.filter_and_split_menu_names(names)
                else:
                    filtered_names = self.filter_menu_names(names)

                for name in filtered_names:
                    meal = Meal(restaurant, name, date, meal_type)
                    meal = self.normalize(meal)

                    if self.is_meal_name_when_normalized(meal.name):
                        # ISSUE#54 220동 이름 오류 수정
                        # ex) ㅁ 바비든든( ~ ): 덮밥류 -> 바비든든: 덮밥류
                        if meal.restaurant == "220동식당":
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
