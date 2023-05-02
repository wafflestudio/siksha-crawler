import asyncio
from base_crawler import *


class AddRestaurantDetail(MealNormalizer):
    def normalize(self, meal, **kwargs):
        details = kwargs.get("restaurant_detail", [])
        final_restaurants = kwargs.get("final_restaurants", [])
        restaurant = meal.restaurant
        for detail in details:
            restaurant = restaurant + ">" + detail
            if text_normalizer(detail, True) in final_restaurants:
                break
        meal.set_restaurant(restaurant)
        return meal


class SnudormRestaurantCrawler(RestaurantCrawler):
    url = "https://snudorm.snu.ac.kr/wp-admin/admin-ajax.php"
    menucost_url = "https://snudorm.snu.ac.kr/food-schedule/"
    restaurant = "기숙사식당"
    normalizer_classes = [FindPrice, FindParenthesisHash, AddRestaurantDetail]

    async def get_menucosts(self):
        urllib3.disable_warnings()
        async with aiohttp.ClientSession(
            headers=self.headers, connector=aiohttp.TCPConnector(ssl=False)
        ) as session:
            async with session.get(self.menucost_url) as response:
                html = await response.read()
                soup = BeautifulSoup(html, "html.parser")
                lis = soup.select("div.board > ul > li")
        prices = {}
        for li in lis:
            spans = li.find_all("span")
            prices[spans[0].text] = spans[1].text
        return prices

    async def run_30days(self):
        date = datetime.datetime.now(timezone("Asia/Seoul")).date()
        menucosts = await self.get_menucosts()
        tasks = [
            self.run(date=date + datetime.timedelta(weeks=i), menucosts=menucosts)
            for i in range(4)
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, date=None, menucosts=None, **kwargs):
        if not date:
            date = datetime.datetime.now(timezone("Asia/Seoul")).date()
        if not menucosts:
            menucosts = await self.get_menucosts()
        urllib3.disable_warnings()
        async with aiohttp.ClientSession(
            headers=self.headers, connector=aiohttp.TCPConnector(ssl=False)
        ) as session:
            data = {
                "action": "metapresso_dorm_food_week_list",
                "start_week_date": date.isoformat(),
                "target_blog": "39",
            }
            async with session.post(self.url, data=data) as response:
                html = await response.read()
                soup = BeautifulSoup(html, "html.parser")
                self.crawl(soup, menucosts=menucosts, **kwargs)

    def crawl(self, soup, menucosts=None, **kwargs):
        if not menucosts:
            menucosts = {}

        trs = soup.select("table > tbody > tr")
        ths = soup.select("table > thead > tr > th")
        dates = [th.text for th in ths[-7:]]
        type = ""
        restaurant_detail = [[] for _ in range(len(trs))]

        for row_idx, tr in enumerate(trs):
            tds = tr.select("td")

            for td in tds[:-7]:
                rowspan = td.attrs.get("rowspan")
                rowspan = int(rowspan[0]) if rowspan else 1
                type_tmp = text_normalizer(td.text)
                if type_tmp in Meal.type_handler:
                    type = type_tmp
                else:
                    for i in range(rowspan):
                        restaurant_detail[row_idx + i].append(td.text)

            for col_idx, td in enumerate(tds[-7:]):
                ul = td.find("ul")
                if ul:
                    for li in ul.find_all("li", recursive=False):
                        spans = li.find_all("span")
                        name = spans[-1].text
                        price = menucosts.get(spans[0].text)
                        restaurant = self.restaurant
                        meal = Meal(restaurant, name, dates[col_idx], type, price)
                        meal = self.normalize(
                            meal,
                            restaurant_detail=restaurant_detail[row_idx],
                            final_restaurants=["아워홈"],
                        )
                        self.found_meal(meal)
