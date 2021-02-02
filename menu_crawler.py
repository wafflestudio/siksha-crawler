from abc import *
import re
import datetime
import requests
from bs4 import BeautifulSoup
from pytz import timezone
import urllib3


def text_normalizer(text, only_letters=False):
    non_letters = [r'\s', '<', '>', r'\(', r'\)', r'\[', r'\]', ',', r'\*', '&', r'\+', r'/', ':']
    text = re.sub(r'\n|\(\)|<>', '', text).strip().strip(':')
    if only_letters:
        text = re.sub('|'.join(non_letters), '', text)
    return text


class Meal:
    BR = 'BR'
    LU = 'LU'
    DN = 'DN'
    type_handler = {BR: BR, LU: LU, DN: DN, '아침': BR, '점심': LU, '저녁': DN, '중식': LU, '석식': DN}
    not_meal = ['휴무', '휴점', '폐점', '제공', '운영']

    def __init__(self, restaurant='', name='', date=None, type='', price=-1, etc=None):
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
            now = datetime.datetime.now(timezone('Asia/Seoul'))
            date = datetime.date.fromtimestamp(now.timestamp())
        if isinstance(date, datetime.date):
            self.date = date
        else:
            year = datetime.datetime.now(timezone('Asia/Seoul')).year
            nums = re.findall(r'\d{1,2}', date)
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
                self.price = -1
            else:
                self.price = int(re.sub(r'\D', '', price))

    def set_etc(self, etc):
        self.etc = etc if etc else []

    @classmethod
    def is_meal_name(cls, name):
        name = text_normalizer(name, True)
        if not name:
            return False
        return name and not any((str in name) for str in cls.not_meal)

    def __str__(self):
        return f"{self.type}> {self.name} | {self.restaurant} | {self.date.isoformat()} | {self.price} | {repr(', '.join(self.etc))}"

    def as_dict(self):
        return dict(
            restaurant_code=self.restaurant,
            code=self.name,
            date=self.date,
            type=self.type,
            price=self.price,
            etc=self.etc
        )


class MealNormalizer(metaclass=ABCMeta):
    @abstractmethod
    def normalize(self, meal, **kwargs):
        pass


class FindPrice(MealNormalizer):
    def normalize(self, meal, **kwargs):
        p = re.compile(r'[1-9]\d{0,2},?\d00원?')
        m = p.search(meal.name)
        if m:
            meal.set_price(m.group())
            meal.set_name(p.sub('', meal.name))
        return meal


class RemoveRestaurantNumber(MealNormalizer):
    def normalize(self, meal, **kwargs):
        meal.set_restaurant(re.sub(r'\(\d{3}-\d{4}\)', '', meal.restaurant))
        return meal


class AddRestaurantDetail(MealNormalizer):
    def normalize(self, meal, **kwargs):
        details = kwargs.get("restaurant_detail", [])
        if details:
            meal.set_restaurant(meal.restaurant + '>' + '>'.join(details))
        return meal


class RemoveInfoFromMealName(MealNormalizer):
    info_sign = ['※', '►', '※']
    def normalize(self, meal, **kwargs):
        meal.set_name(re.sub('(' + '|'.join(self.info_sign) + ').*', '', meal.name))
        return meal


class FindParenthesisHash(MealNormalizer):
    def normalize(self, meal, **kwargs):
        if '(#)' in meal.name:
            meal.set_name(meal.name.replace('(#)', ''))
            meal.etc.append("No meat")
        return meal


class FindRestaurantDetail(MealNormalizer):
    restaurant_regex = [r'(.*)\( ?(\d층.*)\)(.*)', r'(.*)\((.*식당) ?\)(.*)',
                        r'(.*)< ?(\d층.*)>(.*)', r'(.*)<(.*식당) ?>(.*)']

    def normalize(self, meal, **kwargs):
        for regex in self.restaurant_regex:
            m = re.match(regex, meal.name)
            if m:
                meal.set_restaurant(meal.restaurant+ '>' + m.group(2).strip())
                meal.set_name(m.group(1).strip() + m.group(3).strip())
        return meal


class RestaurantCrawler(metaclass=ABCMeta):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0'}
    url = ''
    normalizer_classes = []

    def __init__(self):
        self.meals = []

    @abstractmethod
    def run_30days(self):
        pass

    def run(self, url=None, **kwargs):
        urllib3.disable_warnings()
        if url is None:
            url = self.url
        page = requests.get(url, headers=self.headers, timeout=35, verify=False)
        soup = BeautifulSoup(page.content, 'html.parser')
        self.crawl(soup, **kwargs)

    def normalize(self, meal, **kwargs):
        for normalizer_cls in self.normalizer_classes:
            meal = normalizer_cls().normalize(meal, **kwargs)
        return meal

    def found_meal(self, meal):
        if meal and Meal.is_meal_name(meal.name):
            self.meals.append(meal)

    @abstractmethod
    def crawl(self, soup, **kwargs):
        pass


class VetRestaurantCrawler(RestaurantCrawler):
    url = 'http://vet.snu.ac.kr/node/152'
    restaurant = '수의대식당'

    def run_30days(self):
        self.run()
        return self.meals

    def crawl(self, soup, **kwargs):
        soup.div.extract()
        trs = soup.select('table > tbody > tr')

        types = [th.text for th in trs[0].find_all('th')[1:]]

        for tr in trs[1:]:
            tds = tr.find_all("td")
            date = tds[0].text
            for col_idx, td in enumerate(tds[1:]):
                meal = self.normalize(Meal(self.restaurant, td.text, date, types[col_idx]))
                self.found_meal(meal)


class GraduateDormRestaurantCrawler(RestaurantCrawler):
    url = 'https://dorm.snu.ac.kr/dk_board/facility/food.php'
    restaurant = '기숙사식당'
    normalizer_classes = [FindPrice, AddRestaurantDetail]

    def run_30days(self):
        date = datetime.datetime.now(timezone('Asia/Seoul')).date()
        for i in range(4):
            self.run(date=date+datetime.timedelta(weeks=i))
        return self.meals

    def run(self, date=None, **kwawrgs):
        if not date:
            date = datetime.datetime.now(timezone('Asia/Seoul')).date()
        secs = datetime.datetime.combine(date, datetime.time()) - datetime.datetime(1970, 1, 1, 9)
        url = self.url + "?start_date2=" + str(secs.total_seconds())
        super().run(url)

    def crawl(self, soup, **kwargs):
        trs = soup.select('table > tbody > tr')
        ths = soup.select('table > thead > tr > th')
        lis = soup.select('div.menu > ul > li')

        prices = {}
        for li in lis:
            prices[li.attrs['class'][0]] = li.text
        dates = [th.text for th in ths[-7:]]
        type = ''
        restaurant_detail = [[] for _ in range(len(trs))]

        for row_idx, tr in enumerate(trs):
            tds = tr.find_all('td')
            for td in tds[:-7]:
                rowspan = td.attrs.get('rowspan')
                rowspan = int(rowspan[0]) if rowspan else 1
                type_tmp = text_normalizer(td.text)
                if type_tmp in Meal.type_handler:
                    type = type_tmp
                else:
                    for i in range(rowspan):
                        restaurant_detail[row_idx + i].append(td.text)

            for col_idx, td in enumerate(tds[-7:]):
                for li in td.select('ul > li'):
                    name = li.text
                    menu_type = li.attrs['class']
                    price = prices[menu_type[0]] if menu_type else ''
                    restaurant = self.restaurant
                    meal = Meal(restaurant, name, dates[col_idx], type, price)
                    meal = self.normalize(meal, restaurant_detail=restaurant_detail[row_idx])
                    self.found_meal(meal)


class SnucoRestaurantCrawler(RestaurantCrawler):
    url = 'https://snuco.snu.ac.kr/ko/foodmenu'
    normalizer_classes = [FindPrice, FindParenthesisHash, AddRestaurantDetail, RemoveRestaurantNumber, FindRestaurantDetail, RemoveInfoFromMealName]
    except_restaurant_name_list = ['기숙사식당']
    next_line_keywords = ['테이크아웃']

    def is_next_line_keyword(self, name):
        code = text_normalizer(name, True)
        return any((str == code) for str in self.next_line_keywords)

    def should_combine(self, last_meal, meal):
        if not last_meal:
            return False
        return self.is_next_line_keyword(last_meal.name)\
               or (meal.price == -1 and not self.is_next_line_keyword(meal.name))

    def combine(self, last_meal, meal):
        if not last_meal:
            return meal
        if not meal:
            return last_meal
        last_meal.set_name(last_meal.name + ': ' + meal.name)
        if last_meal.price == -1:
            last_meal.set_price(meal.price)
        return last_meal

    def run_30days(self):
        date = datetime.datetime.now(timezone('Asia/Seoul')).date()
        for i in range(30):
            self.run(date=date+datetime.timedelta(days=i))
        return self.meals

    def run(self, date=None, **kwargs):
        if not date:
            date = datetime.datetime.now(timezone('Asia/Seoul')).date()
        url = self.url + f'?field_menu_date_value_1%5Bvalue%5D%5Bdate%5D=&field_menu_date_value%5Bvalue%5D%5Bdate%5D={date.month}%2F{date.day}%2F{date.year}'
        super().run(url, date=date, **kwargs)

    def crawl(self, soup, **kwargs):
        date = kwargs.get("date", datetime.datetime.now(timezone('Asia/Seoul')).date())
        table = soup.select_one('div.view-content > table')
        if not table:
            return
        ths = table.select('thead > tr > th')
        trs = table.select('tbody > tr')

        types = []
        for th in ths[1:]:
            types.append(th.text)

        for tr in trs:
            tds = tr.select('td')
            restaurant = tds[0].text
            if any((except_restaurant_name in restaurant) for except_restaurant_name in self.except_restaurant_name_list):
                continue
            for col_idx, td in enumerate(tds[1:]):
                ps = td.select('p')
                restaurant_detail = []
                last_meal = None
                for p in ps:
                    for name in p.text.split('\n'):
                        meal = Meal(restaurant, name, date, types[col_idx])
                        meal = self.normalize(meal, restaurant_detail=restaurant_detail)

                        if Meal.is_meal_name(meal.name):
                            if self.should_combine(last_meal, meal):
                                last_meal = self.combine(last_meal, meal)
                            else:
                                self.found_meal(last_meal)
                                last_meal = meal
                        else:
                            self.found_meal(last_meal)
                            last_meal = None
                if last_meal:
                    self.found_meal(last_meal)


def print_meals(meals):
    print('[')
    for meal in meals:
        print('\t' + str(meal))
    print(']')
    print('total #:', len(meals))


#print_meals(VetRestaurantCrawler().run_30days())
#print_meals(GraduateDormRestaurantCrawler().run_30days())
#print_meals(SnucoRestaurantCrawler().run_30days())

#snuco = SnucoRestaurantCrawler()
#snuco.run(date=datetime.date(2021, 2, 3))
#print_meals(snuco.meals)
