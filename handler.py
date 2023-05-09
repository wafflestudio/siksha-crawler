from distutils.debug import DEBUG
import pymysql
import os
import datetime
from pytz import timezone
from itertools import compress
import asyncio
import argparse
from slack import send_slack_message
from crawlers.base_crawler import text_normalizer
from crawlers.vet_crawler import VetRestaurantCrawler
from crawlers.snudorm_crawler import SnudormRestaurantCrawler
from crawlers.snuco_crawler import SnucoRestaurantCrawler


def compare_restaurants(db_restaurants, crawled_meals):
    codes = [restaurant.get("code") for restaurant in db_restaurants]
    new_restaurants = []
    for meal in crawled_meals:
        code = text_normalizer(meal.restaurant, True)
        if code not in codes:
            new_restaurants.append(
                dict(
                    code=code,
                    name_kr=meal.restaurant,
                )
            )
            codes.append(code)
    return new_restaurants


def remove_duplicate(menus):
    unique_fields = ["restaurant_id", "code", "date", "type"]
    unique = [True] * len(menus)
    for i in range(len(menus)):
        for j in range(i):
            if all(
                (menus[i].get(field) == menus[j].get(field)) for field in unique_fields
            ):
                unique[i] = False
                break
    return list(compress(menus, unique))


def compare_menus(db_menus, crawled_meals, restaurants):
    unique_fields = ["restaurant_id", "code", "date", "type"]
    detail_fields = ["price", "etc"]
    restaurant_dict = {
        restaurant.get("code"): restaurant.get("id") for restaurant in restaurants
    }
    crawled_menus = [meal.as_dict() for meal in crawled_meals]
    for menu in crawled_menus:
        restaurant_code = text_normalizer(menu.pop("restaurant"), True)
        menu["restaurant_id"] = restaurant_dict.get(restaurant_code)
        name = menu.pop("name")
        menu["name_kr"] = name
        menu["code"] = text_normalizer(name, True)

    crawled_menus = remove_duplicate(crawled_menus)

    db_not_found = [True] * len(db_menus)
    crawled_not_found = [True] * len(crawled_menus)
    edited = [False] * len(db_menus)
    for db_idx in range(len(db_menus)):
        for crawled_idx in range(len(crawled_menus)):
            if all(
                (
                    db_menus[db_idx].get(field, None)
                    == crawled_menus[crawled_idx].get(field)
                )
                for field in unique_fields
            ):
                db_not_found[db_idx] = False
                crawled_not_found[crawled_idx] = False
                for field in detail_fields:
                    if db_menus[db_idx].get(field, None) != crawled_menus[
                        crawled_idx
                    ].get(field):
                        edited[db_idx] = True
                        db_menus[db_idx]["previous_" + field] = db_menus[db_idx].pop(
                            field, None
                        )
                        db_menus[db_idx][field] = crawled_menus[crawled_idx].get(field)
                break
    return (
        list(compress(crawled_menus, crawled_not_found)),
        list(compress(db_menus, db_not_found)),
        list(compress(db_menus, edited)),
    )


def send_new_restaurants_message(new_restaurants):
    print(f"New restaurants: {repr(new_restaurants)}")
    if new_restaurants:
        slack_message = f"{len(new_restaurants)} new restaurants found: "
        for restaurant in new_restaurants:
            slack_message = slack_message + '"' + restaurant.get("name_kr") + '" '
        send_slack_message(slack_message)


def restaurants_transaction(crawled_meals, cursor):
    get_restaurants_query = """
        SELECT code
        FROM restaurant;
    """
    cursor.execute(get_restaurants_query)
    db_restaurants = cursor.fetchall()
    new_restaurants = compare_restaurants(db_restaurants, crawled_meals)
    send_new_restaurants_message(new_restaurants)
    insert_restaurants_query = """
        INSERT INTO restaurant(code, name_kr)
        VALUES (%(code)s, %(name_kr)s);
    """
    cursor.executemany(insert_restaurants_query, new_restaurants)
    print("Restaurants checked")


def send_deleted_menus_message(deleted_menus):
    print(f"Menus deleted: {repr(deleted_menus)}")
    if deleted_menus:
        send_slack_message(f"{len(deleted_menus)} menus deleted: {repr(deleted_menus)}")


def send_new_menus_message(new_menus):
    slack_message = f"{len(new_menus)} new menus found: "
    for menu in new_menus:
        name_kr = menu.get("name_kr")
        if ":" in name_kr:
            slack_message = slack_message + '*"' + menu.get("name_kr") + '"* '
        else:
            slack_message = slack_message + '"' + menu.get("name_kr") + '" '
    send_slack_message(slack_message)
    print(f"New menus found: {repr(new_menus)}")


def send_edited_menus_message(edited_menus):
    print(f"Menus edited: {repr(edited_menus)}")
    if edited_menus:
        send_slack_message(f"{len(edited_menus)} menus edited: {repr(edited_menus)}")


def menus_transaction(crawled_meals, cursor):
    get_restaurants_query = """
        SELECT id, code
        FROM restaurant;
    """
    cursor.execute(get_restaurants_query)
    restaurants = cursor.fetchall()
    today = datetime.datetime.now(timezone("Asia/Seoul")).date()
    get_menus_query = f"""
        SELECT id, restaurant_id, code, date, type, price, etc, name_kr
        FROM menu
        WHERE date>='{today.isoformat()}';
    """
    cursor.execute(get_menus_query)
    db_menus = cursor.fetchall()

    new_menus, deleted_menus, edited_menus = compare_menus(
        db_menus, crawled_meals, restaurants
    )

    send_deleted_menus_message(deleted_menus)
    if deleted_menus:
        deleted_menus_id = [str(menu.get("id")) for menu in deleted_menus]
        delete_menus_query = f"""
            DELETE FROM menu
            WHERE id in ({','.join(deleted_menus_id)});
        """
        cursor.execute(delete_menus_query)

    send_new_menus_message(new_menus)
    insert_menus_query = """
        INSERT INTO menu(restaurant_id, code, date, type, name_kr, price, etc)
        VALUES (%(restaurant_id)s, %(code)s, %(date)s, %(type)s, %(name_kr)s, %(price)s, %(etc)s);
    """
    cursor.executemany(insert_menus_query, new_menus)

    send_edited_menus_message(edited_menus)
    edited_menus_query = """
        UPDATE menu
        SET price=%(price)s, etc=%(etc)s, name_kr=%(name_kr)s
        WHERE id=%(id)s;
    """
    cursor.executemany(edited_menus_query, edited_menus)

    print("Menus checked")


async def run_crawlers(crawlers):
    tasks = [asyncio.create_task(crawler.run_30days()) for crawler in crawlers]
    return await asyncio.gather(*tasks, return_exceptions=True)


def crawl_debug(**kwargs):

    arg_date = kwargs.get("date")
    arg_restaurant = kwargs.get("restaurant")

    crawlers = [
        VetRestaurantCrawler(),
        SnudormRestaurantCrawler(),
        SnucoRestaurantCrawler(),
    ]
    results = asyncio.run(run_crawlers(crawlers))
    for result in results:
        for err in result:
            if err is not None:
                raise err
    crawled_meals = []
    for crawler in crawlers:
        crawled_meals = crawled_meals + crawler.meals

    today = datetime.datetime.now(timezone("Asia/Seoul")).date()

    if arg_date is not None:
        ndate = datetime.datetime(
            int(arg_date[:4]), int(arg_date[4:6]), int(arg_date[6:])
        ).date()

        crawled_meals = list(
            filter(
                lambda meal: (meal.date == ndate and arg_restaurant in meal.restaurant),
                crawled_meals,
            )
        )

    else:
        crawled_meals = list(
            filter(
                lambda meal: (meal.date >= today and arg_restaurant in meal.restaurant),
                crawled_meals,
            )
        )

    crawled_menus = [print(meal.as_dict()) for meal in crawled_meals]


def crawl(event, context):
    siksha_db = pymysql.connect(
        user=os.environ.get("DB_USER", "root"),
        passwd=os.environ.get("DB_PASSWORD", "waffle"),
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        db=os.environ.get("DB_NAME", "siksha"),
        charset="utf8",
    )
    cursor = siksha_db.cursor(pymysql.cursors.DictCursor)
    try:
        print("Start crawling")
        crawlers = [
            VetRestaurantCrawler(),
            SnudormRestaurantCrawler(),
            SnucoRestaurantCrawler(),
        ]
        results = asyncio.run(run_crawlers(crawlers))
        for result in results:
            for err in result:
                if err is not None:
                    raise err
        crawled_meals = []
        for crawler in crawlers:
            crawled_meals = crawled_meals + crawler.meals
        today = datetime.datetime.now(timezone("Asia/Seoul")).date()
        crawled_meals = list(filter(lambda meal: meal.date >= today, crawled_meals))
        restaurants_transaction(crawled_meals, cursor)
        siksha_db.commit()
        menus_transaction(crawled_meals, cursor)
        siksha_db.commit()

        send_slack_message("Crawling has been successfully done")
        return "Crawling has been successfully done"
    except Exception as e:
        siksha_db.rollback()
        print(e)
        send_slack_message("Crawling has been failed")
        return "Crawling has been failed"
    finally:
        cursor.close()
        siksha_db.close()


if __name__ == "__main__":

    # Parse args for debug
    parser = argparse.ArgumentParser(description="debug option")
    parser.add_argument("--restaurant", "-r", help="어떤 식당? 예시)자하연")
    parser.add_argument("--date", "-d", help="언제? 예시)20221012")
    args = parser.parse_args()

    if args.restaurant is not None:
        crawl_debug(restaurant=args.restaurant, date=args.date)
    else:
        crawl(None, None)
