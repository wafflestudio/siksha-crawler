import json
import pymysql
import os
import random
from slack import send_slack_message
from menu_crawler import text_normalizer, VetRestaurantCrawler, GraduateDormRestaurantCrawler, SnucoRestaurantCrawler


def compare_restaurants(db_restaurants, crawled_menus):
    codes = [rest.get('code') for rest in db_restaurants]
    new_restaurants = []
    for menu in crawled_menus:
        code = text_normalizer(menu.restaurant, True)
        if code not in codes:
            new_restaurants.append(dict(
                code=code,
                name_kr=menu.restaurant,
            ))
            codes.append(code)
    return new_restaurants


def crawl(event, context):
    try:
        siksha_db = pymysql.connect(
            user=os.environ.get('DB_USER', 'root'),
            passwd=os.environ.get('DB_PASSWORD', 'waffle'),
            host=os.environ.get('DB_HOST', '127.0.0.1'),
            db=os.environ.get('DB_NAME', 'siksha'),
            charset='utf8'
        )
        cursor = siksha_db.cursor(pymysql.cursors.DictCursor)
        # TRANSACTION START
        get_restaurants_query = """
            SELECT *
            FROM restaurant
        """
        cursor.execute(get_restaurants_query)
        db_restaurants = cursor.fetchall()
        crawled_menus = VetRestaurantCrawler().run_30days() \
                        + GraduateDormRestaurantCrawler().run_30days() \
                        + SnucoRestaurantCrawler().run_30days()
        new_restaurants = compare_restaurants(db_restaurants, crawled_menus)
        print(f"New Restaurants: {repr(new_restaurants)}")
        if new_restaurants:
            slack_message = "New Restaurant Found: "
            for restaurant in new_restaurants:
                slack_message = slack_message + '"' + restaurant.get('name_kr') + '" '
            send_slack_message(slack_message)
            insert_restaurants_query = """
                INSERT INTO restaurant(code, name_kr)
                VALUES (%(code)s, %(name_kr)s);
            """
            cursor.executemany(insert_restaurants_query, new_restaurants)
        # TRANSACTION END
        siksha_db.commit()
        send_slack_message("crawling has been successfully done")
        return "crawling has been successfully done"
    except:
        siksha_db.rollback()
        send_slack_message("crawling has been failed")
        return "crawling has been failed"


crawl(None, None)
