from abc import *
import re
import datetime
import requests
from bs4 import BeautifulSoup
from pytz import timezone
import urllib3


def text_normalizer(text, remove_space=False):
    text = re.sub(r'\n|\(\)|<>', '', text).strip()
    if remove_space:
        text = re.sub(r'\s', '', text)
    return text


class Meal:
    BR = 'BR'
    LU = 'LU'
    DN = 'DN'
    type_handler = {BR: BR, LU: LU, DN: DN, '아침': BR, '점심': LU, '저녁': DN, '중식': LU, '석식': DN}
    not_meal = ['휴무', '휴점', '폐점', '제공']

    def __init__(self, type='', meal_name='', restaurant='', restaurant_detail=None, date=None, price=-1, etc=None):
        self.set_type(type)
        self.set_meal_name(meal_name)
        self.set_restaurant(restaurant)
        self.set_restaurant_detail(restaurant_detail)
        self.set_date(date)
        self.set_price(price)
        self.set_etc(etc)

    def set_type(self, type):
        self.type = self.type_handler.get(text_normalizer(type, True))

    def set_meal_name(self, meal_name):
        self.meal_name = text_normalizer(meal_name)

    def set_restaurant(self, restaurant):
        self.restaurant = text_normalizer(restaurant)

    def set_restaurant_detail(self, restaurant_detail):
        self.restaurant_detail = restaurant_detail if restaurant_detail else []

    def set_date(self, date):
        if isinstance(date, datetime.date):
            self.date = date
        else:
            year = datetime.datetime.now(timezone('Asia/Seoul')).year
            nums = re.findall(r'\d{1,2}', date)
            month = int(nums[0])
            day = int(nums[1])
            self.date = datetime.date(year, month, day)

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
    def is_meal_name(cls, meal_name):
        meal_name = text_normalizer(meal_name, True)
        if not meal_name:
            return False
        for str in cls.not_meal:
            if str in meal_name:
                return False
        return True

    def __str__(self):
        restaurant_name = self.restaurant
        if self.restaurant_detail:
            restaurant_name = restaurant_name + '(' + '>'.join(self.restaurant_detail) + ')'
        return f"{self.type}> {self.meal_name} | {restaurant_name} | {self.date.isoformat()} | {self.price} | {repr(', '.join(self.etc))}"


class MealNormalizer(metaclass=ABCMeta):
    @abstractmethod
    def normalize(self, meal, **kwargs):
        pass


class FindPrice(MealNormalizer):
    def normalize(self, meal, **kwargs):
        p = re.compile(r'[1-9]\d{0,2},?\d00원?')
        m = p.search(meal.meal_name)
        if m:
            meal.set_price(m.group())
            meal.set_meal_name(p.sub('', meal.meal_name))
        return meal


class RemoveRestaurantNumber(MealNormalizer):
    def normalize(self, meal, **kwargs):
        meal.set_restaurant(re.sub(r'\(\d{3}-\d{4}\)', '', meal.restaurant))
        return meal


class RemoveInfoFromMealName(MealNormalizer):
    info_sign = ['※', '►', '※']
    def normalize(self, meal, **kwargs):
        meal.set_meal_name(re.sub('(' + '|'.join(self.info_sign) + ').*', '', meal.meal_name))
        return meal


class FindParenthesisHash(MealNormalizer):
    def normalize(self, meal, **kwargs):
        if '(#)' in meal.meal_name:
            meal.set_meal_name(meal.meal_name.replace('(#)', ''))
            meal.etc.append("No meat")
        return meal


class FindRestaurantDetail(MealNormalizer):
    restaurant_regex = [r'(.*)\( ?(\d층.*)\)(.*)', r'(.*)\((.*식당) ?\)(.*)',
                        r'(.*)< ?(\d층.*)>(.*)', r'(.*)<(.*식당) ?>(.*)']

    def normalize(self, meal, **kwargs):
        for regex in self.restaurant_regex:
            m = re.match(regex, meal.meal_name)
            if m:
                meal.restaurant_detail.append(text_normalizer(m.group(2)))
                meal.set_meal_name(m.group(1)+m.group(3))
        return meal


class RestaurantCrawler(metaclass=ABCMeta):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0'}
    url = ''
    normalizer_classes = []

    def run(self, url=None):
        urllib3.disable_warnings()
        if url is None:
            url = self.url
        page = requests.get(url, headers=self.headers, timeout=35, verify=False)
        soup = BeautifulSoup(page.content, 'html.parser')
        self.crawl(soup)

    def normalize(self, meal, **kwargs):
        for normalizer_cls in self.normalizer_classes:
            meal = normalizer_cls().normalize(meal, **kwargs)
        return meal

    def print_meal(self, meal):
        if Meal.is_meal_name(meal.meal_name):
            print(meal)

    @abstractmethod
    def crawl(self, soup):
        pass


class VetRestaurantCrawler(RestaurantCrawler):
    url = 'http://vet.snu.ac.kr/node/152'
    restaurant = '수의대식당'

    def crawl(self, soup):
        soup.div.extract()
        trs = soup.select('table > tbody > tr')

        types = [th.text for th in trs[0].find_all('th')[1:]]

        for tr in trs[1:]:
            tds = tr.find_all("td")
            date = tds[0].text
            for col_idx, td in enumerate(tds[1:]):
                meal = self.normalize(Meal(types[col_idx], td.text, self.restaurant, date=date))
                self.print_meal(meal)


class GraduateDormRestaurantCrawler(RestaurantCrawler):
    url = 'https://dorm.snu.ac.kr/dk_board/facility/food.php'
    restaurant = '기숙사식당'
    normalizer_classes = [FindPrice,]

    def run(self, date=None):
        if not date:
            date = datetime.datetime.now(timezone('Asia/Seoul')).date()
        secs = datetime.datetime.combine(date, datetime.time()) - datetime.datetime(1970, 1, 1, 9)
        url = self.url + "?start_date2=" + str(secs.total_seconds())
        super().run(url)

    def crawl(self, soup):
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
                    meal_name = li.text
                    menu_type = li.attrs['class']
                    price = prices[menu_type[0]] if menu_type else ''
                    meal = Meal(type, meal_name, self.restaurant, restaurant_detail[row_idx], dates[col_idx], price)
                    meal = self.normalize(meal)
                    self.print_meal(meal)


class SnucoRestaurantCrawler(RestaurantCrawler):
    url = 'https://snuco.snu.ac.kr/ko/foodmenu'
    normalizer_classes = [FindPrice, FindParenthesisHash, RemoveRestaurantNumber, FindRestaurantDetail, RemoveInfoFromMealName]
    except_restaurant_name_list = ['기숙사식당']

    def run(self, date=None):
        self.date = date if date else datetime.datetime.now(timezone('Asia/Seoul')).date()
        url = self.url + f'?field_menu_date_value_1%5Bvalue%5D%5Bdate%5D=&field_menu_date_value%5Bvalue%5D%5Bdate%5D={self.date.month}%2F{self.date.day}%2F{self.date.year}'
        super().run(url)

    def date_normalizer(self, date):
        return date.isoformat()

    def crawl(self, soup):
        table = soup.select_one('div.view-content > table')
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
                    for meal_name in p.text.split('\n'):
                        meal = Meal(types[col_idx], meal_name, restaurant, None, self.date, -1)
                        meal = self.normalize(meal)
                        if meal.restaurant_detail:
                            restaurant_detail = meal.restaurant_detail
                        else:
                            meal.restaurant_detail = restaurant_detail

                        if Meal.is_meal_name(meal.meal_name):
                            if meal.price == -1:
                                if last_meal:
                                    last_meal.set_meal_name(f'{last_meal.meal_name}: {meal.meal_name}')
                                else:
                                    last_meal = meal
                            else:
                                if last_meal:
                                    self.print_meal(last_meal)
                                last_meal = meal
                        else:
                            if last_meal:
                                self.print_meal(last_meal)
                                last_meal = None
                if last_meal:
                    self.print_meal(last_meal)



#VetRestaurantCrawler().run()
#GraduateDormRestaurantCrawler().run()
#GraduateDormRestaurantCrawler().run(datetime.date(2021, 1, 31))
SnucoRestaurantCrawler().run()
#SnucoRestaurantCrawler().run(datetime.date(2021, 1, 28))
