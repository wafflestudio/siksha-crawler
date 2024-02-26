import asyncio
from crawlers.base_crawler import RestaurantCrawler, Meal


class VetRestaurantCrawler(RestaurantCrawler):
    url = "https://vet.snu.ac.kr/금주의-식단/"
    restaurant = "수의대식당"

    async def run_30days(self):
        return await asyncio.gather(self.run(), return_exceptions=True)

    def crawl(self, soup, **kwargs):
        soup.div.extract()
        trs = soup.select("table > tbody > tr")

        types = [th.text for th in trs[0].find_all("th")[1:]]

        for tr in trs[1:]:
            tds = tr.find_all("td")
            date = tds[0].text
            for col_idx, td in enumerate(tds[1:]):
                meal = self.normalize(Meal(self.restaurant, td.text, date, types[col_idx]))
                self.found_meal(meal)
