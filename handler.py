import json
import pymysql
import os
import datetime
from pytz import timezone
from itertools import compress
from slack import send_slack_message
from menu_crawler import text_normalizer, VetRestaurantCrawler, GraduateDormRestaurantCrawler, SnucoRestaurantCrawler


def compare_restaurants(db_restaurants, crawled_meals):
    codes = [restaurant.get('code') for restaurant in db_restaurants]
    new_restaurants = []
    for meal in crawled_meals:
        code = text_normalizer(meal.restaurant, True)
        if code not in codes:
            new_restaurants.append(dict(
                code=code,
                name_kr=meal.restaurant,
            ))
            codes.append(code)
    return new_restaurants


def compare_menus(db_menus, crawled_meals, restaurants):
    fields = ['restaurant_id', 'code', 'date', 'type', 'price', 'etc']
    restaurant_dict = {restaurant.get('code'): restaurant.get('id') for restaurant in restaurants}
    crawled_menus = [meal.as_dict() for meal in crawled_meals]
    for menu in crawled_menus:
        restaurant_code = text_normalizer(menu.pop('restaurant'), True)
        menu['restaurant_id'] = restaurant_dict.get(restaurant_code)
        name = menu.pop('name')
        menu['name_kr'] = name
        menu['code'] = text_normalizer(name, True)

    db_not_found = [True] * len(db_menus)
    crawled_not_found = [True] * len(crawled_menus)
    for db_idx in range(len(db_menus)):
        for crawled_idx in range(len(crawled_menus)):
            if all((db_menus[db_idx].get(field, None) == crawled_menus[crawled_idx].get(field)) for field in fields):
                db_not_found[db_idx] = False
                crawled_not_found[crawled_idx] = False
    return list(compress(crawled_menus, crawled_not_found)), list(compress(db_menus, db_not_found))


def restaurants_transaction(crawled_meals, cursor):
    get_restaurants_query = """
        SELECT code
        FROM restaurant;
    """
    cursor.execute(get_restaurants_query)
    db_restaurants = cursor.fetchall()
    new_restaurants = compare_restaurants(db_restaurants, crawled_meals)
    print(f"New Restaurants: {repr(new_restaurants)}")
    if new_restaurants:
        slack_message = "New Restaurant(s) Found: "
        for restaurant in new_restaurants:
            slack_message = slack_message + '"' + restaurant.get('name_kr') + '" '
        send_slack_message(slack_message)
        insert_restaurants_query = """
            INSERT INTO restaurant(code, name_kr)
            VALUES (%(code)s, %(name_kr)s);
        """
        cursor.executemany(insert_restaurants_query, new_restaurants)
    print("Restaurants checked")


def menus_transaction(crawled_meals, cursor):
    get_restaurants_query = """
        SELECT id, code
        FROM restaurant;
    """
    cursor.execute(get_restaurants_query)
    restaurants = cursor.fetchall()
    today = datetime.datetime.now(timezone('Asia/Seoul')).date()
    get_menus_query = f"""
        SELECT id, restaurant_id, code, date, type, price, etc
        FROM menu
        WHERE date>='{today.isoformat()}';
    """
    cursor.execute(get_menus_query)
    db_menus = cursor.fetchall()

    new_menus, deleted_menus = compare_menus(db_menus, crawled_meals, restaurants)

    print(f"{len(deleted_menus)} Deleted menus found: {repr(deleted_menus)}")
    if deleted_menus:
        send_slack_message(f"{len(deleted_menus)} Deleted menus found: {repr(deleted_menus)}")
        deleted_menus_id = [str(menu.get('id')) for menu in deleted_menus]
        delete_menus_query = f"""
            DELETE FROM menu
            WHERE id in ({','.join(deleted_menus_id)});
        """
        cursor.execute(delete_menus_query)

    send_slack_message(f"{len(new_menus)} New menus found.")
    print(f"{len(new_menus)} New menus found: {repr(new_menus)}")
    new_menus_to_check = list(filter(lambda menu: ':' in menu.get('name_kr'), new_menus))
    if new_menus_to_check:
        send_slack_message(f"{len(new_menus_to_check)} New menus to be checked: {repr(new_menus_to_check)}")
    insert_menus_query = """
        INSERT INTO menu(restaurant_id, code, date, type, name_kr, price, etc)
        VALUES (%(restaurant_id)s, %(code)s, %(date)s, %(type)s, %(name_kr)s, %(price)s, %(etc)s);
    """
    cursor.executemany(insert_menus_query, new_menus)

    print("Menus checked")


def crawl(event, context):
    try:
        print("Start crawling")
        siksha_db = pymysql.connect(
            user=os.environ.get('DB_USER', 'root'),
            passwd=os.environ.get('DB_PASSWORD', 'waffle'),
            host=os.environ.get('DB_HOST', '127.0.0.1'),
            db=os.environ.get('DB_NAME', 'siksha'),
            charset='utf8'
        )
        cursor = siksha_db.cursor(pymysql.cursors.DictCursor)

        crawled_meals = VetRestaurantCrawler().run_30days() \
                        + GraduateDormRestaurantCrawler().run_30days() \
                        + SnucoRestaurantCrawler().run_30days()
        today = datetime.datetime.now(timezone('Asia/Seoul')).date()
        crawled_meals = list(filter(lambda meal: meal.date >= today, crawled_meals))
        restaurants_transaction(crawled_meals, cursor)
        siksha_db.commit()
        menus_transaction(crawled_meals, cursor)
        siksha_db.commit()

        send_slack_message("Crawling has been successfully done")
        return "Crawling has been successfully done"
    except:
        siksha_db.rollback()
        send_slack_message("Crawling has been failed")
        return "Crawling has been failed"


#crawl(None, None)
