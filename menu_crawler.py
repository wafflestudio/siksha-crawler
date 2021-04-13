from abc import *
import re
import datetime
import requests
from bs4 import BeautifulSoup
from pytz import timezone
import urllib3
import json
import asyncio
import aiohttp


def text_normalizer(text, only_letters=False):
    non_letters = [r'\s', '<', '>', r'\(', r'\)', r'\[', r'\]', ',', r'\*', '&', r'\+', '-', r'/', ':', '#', r'\.']
    text = re.sub(r'\n|\(\)|<>', '', text).strip().strip(':')
    text = re.sub(r'\xa0', ' ', text)
    if only_letters:
        text = re.sub('|'.join(non_letters), '', text)
    return text


class Meal:
    BR = 'BR'
    LU = 'LU'
    DN = 'DN'
    type_handler = {BR: BR, LU: LU, DN: DN, '아침': BR, '점심': LU, '저녁': DN, '중식': LU, '석식': DN}
    not_meal = ['휴무', '휴점', '폐점', '휴업', '제공', '미운영', 'won', '한달간', '구독서비스', '월\d*회']

    def __init__(self, restaurant='', name='', date=None, type='', price=None, etc=None):
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
                self.price = None
            else:
                self.price = int(re.sub(r'\D', '', price))

    def set_etc(self, etc):
        self.etc = etc if etc else []

    @classmethod
    def is_meal_name(cls, name):
        name = text_normalizer(name, True)
        if not name:
            return False
        return name and all(re.match('.*' + p + '.*', name) is None for p in cls.not_meal)

    def __str__(self):
        return f"{self.type}> {self.name} | {self.restaurant} | {self.date.isoformat()} | {self.price} | {repr(', '.join(self.etc))}"

    def as_dict(self):
        return dict(
            restaurant=self.restaurant,
            name=self.name,
            date=self.date,
            type=self.type,
            price=self.price,
            etc=json.dumps(self.etc)
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
        final_restaurants = kwargs.get("final_restaurants", [])
        restaurant = meal.restaurant
        for detail in details:
            restaurant = restaurant + '>' + detail
            if text_normalizer(detail, True) in final_restaurants:
                break
        meal.set_restaurant(restaurant)
        return meal


class RemoveInfoFromMealName(MealNormalizer):
    info_sign = ['※', '►', '※', '브레이크 타임']
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
                        r'(.*)< ?(\d층.*)>(.*)', r'(.*)<(.*식당) ?>(.*)',
                        r'(.*)<(테이크아웃)>(.*)']

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

    async def run(self, url=None, **kwargs):
        urllib3.disable_warnings()
        if url is None:
            url = self.url
        async with aiohttp.ClientSession(headers=self.headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.get(url) as response:
                html = await response.read()
                soup = BeautifulSoup(html, 'html.parser')
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

    async def run_30days(self):
        await self.run()

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


class SnudormRestaurantCrawler(RestaurantCrawler):
    url = 'https://snudorm.snu.ac.kr/wp-admin/admin-ajax.php'
    menucost_url = 'https://snudorm.snu.ac.kr/food-schedule/'
    restaurant = '기숙사식당'
    normalizer_classes = [FindPrice, FindParenthesisHash, AddRestaurantDetail]

    async def get_menucosts(self):
        urllib3.disable_warnings()
        async with aiohttp.ClientSession(headers=self.headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.get(self.menucost_url) as response:
                html = await response.read()
                soup = BeautifulSoup(html, 'html.parser')
                lis = soup.select('div.board > ul > li')
        prices = {}
        for li in lis:
            spans = li.find_all('span')
            prices[spans[0].text] = spans[1].text
        return prices


    async def run_30days(self):
        date = datetime.datetime.now(timezone('Asia/Seoul')).date()
        menucosts = await self.get_menucosts()
        tasks = [asyncio.create_task(self.run(date=date+datetime.timedelta(weeks=i), menucosts=menucosts)) for i in range(4)]
        await asyncio.wait(tasks)

    async def run(self, date=None, menucosts=None, **kwargs):
        if not date:
            date = datetime.datetime.now(timezone('Asia/Seoul')).date()
        if not menucosts:
            menucosts = await self.get_menucosts()
        urllib3.disable_warnings()
        async with aiohttp.ClientSession(headers=self.headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
            data = {'action': 'metapresso_dorm_food_week_list', 'start_week_date': date.isoformat(), 'target_blog': '39'}
            async with session.post(self.url, data=data) as response:
                html = await response.read()
                soup = BeautifulSoup(html, 'html.parser')
                self.crawl(soup, menucosts=menucosts, **kwargs)


    def crawl(self, soup, menucosts=None, **kwargs):
        if not menucosts:
            menucosts = {}

        trs = soup.select('table > tbody > tr')
        ths = soup.select('table > thead > tr > th')
        dates = [th.text for th in ths[-7:]]
        type = ''
        restaurant_detail = [[] for _ in range(len(trs))]

        for row_idx, tr in enumerate(trs):
            tds = tr.select('td')
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
                ul = td.find('ul')
                if ul:
                    for li in ul.find_all('li', recursive=False):
                        spans = li.find_all('span')
                        name = spans[1].text
                        price = menucosts.get(spans[0].text)
                        restaurant = self.restaurant
                        meal = Meal(restaurant, name, dates[col_idx], type, price)
                        meal = self.normalize(meal, restaurant_detail=restaurant_detail[row_idx], final_restaurants = ['아워홈'])
                        self.found_meal(meal)


class SnucoRestaurantCrawler(RestaurantCrawler):
    url = 'https://snuco.snu.ac.kr/ko/foodmenu'
    normalizer_classes = [FindPrice, FindParenthesisHash, RemoveRestaurantNumber, FindRestaurantDetail, RemoveInfoFromMealName]
    except_restaurant_name_list = ['기숙사식당']
    next_line_keywords = ['봄', '소반', '콤비메뉴', '셀프코너', '오늘의메뉴', '채식뷔페', '추가코너']
    multi_line_keywords = {'+': ['셀프코너'], ' / ': ['추가코너']}

    def is_next_line_keyword(self, meal):
        if not meal:
            return False
        code = text_normalizer(meal.name, True)
        return any((str == code) for str in self.next_line_keywords)

    def get_multi_line_delimiter(self, meal):
        if not meal:
            return None
        code = text_normalizer(meal.name, True)
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
        date = datetime.datetime.now(timezone('Asia/Seoul')).date()
        tasks = [asyncio.create_task(self.run(date=date+datetime.timedelta(days=i))) for i in range(30)]
        await asyncio.wait(tasks)

    async def run(self, date=None, **kwargs):
        if not date:
            date = datetime.datetime.now(timezone('Asia/Seoul')).date()
        url = self.url + f'?field_menu_date_value_1%5Bvalue%5D%5Bdate%5D=&field_menu_date_value%5Bvalue%5D%5Bdate%5D={date.month}%2F{date.day}%2F{date.year}'
        await super().run(url, date=date, **kwargs)

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
            row_restaurant = tds[0].text
            if any((except_restaurant_name in row_restaurant) for except_restaurant_name in self.except_restaurant_name_list):
                continue
            for col_idx, td in enumerate(tds[1:]):
                ps = td.select('p')
                restaurant = row_restaurant
                last_meal = None
                for p in ps:
                    for name in p.text.split('\n'):
                        meal = Meal(restaurant, name, date, types[col_idx])
                        meal = self.normalize(meal)

                        if Meal.is_meal_name(meal.name):
                            if self.is_next_line_keyword(last_meal):
                                last_meal = self.combine(last_meal, meal)
                            else:
                                delimiter = self.get_multi_line_delimiter(last_meal)
                                if delimiter is not None:
                                    last_meal = self.combine(last_meal, meal, delimiter)
                                else:
                                    self.found_meal(last_meal)
                                    last_meal = meal
                        elif self.get_multi_line_delimiter(last_meal) is None:
                            if meal.restaurant != restaurant:
                                meal = Meal(row_restaurant, name, date, types[col_idx])
                                meal = self.normalize(meal)
                                restaurant = meal.restaurant
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


#crawler = SnucoRestaurantCrawler()
#asyncio.run(crawler.run(date = datetime.date(2021, 4, 8)))
#print_meals(crawler.meals)
