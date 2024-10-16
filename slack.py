import os

import requests


def _send_slack_message(message: str):
    slack_token = os.environ.get("SLACK_TOKEN")
    slack_channel = os.environ["SLACK_CHANNEL"]
    if not slack_token:
        print("No Slack token provided. Skipping sending message.")
        return
    body = {"channel": slack_channel, "text": message}
    headers = {"Authorization": f"Bearer {slack_token}"}
    try:
        res = requests.post("https://slack.com/api/chat.postMessage", headers=headers, data=body, timeout=100)
        res.raise_for_status()
    except Exception as e:
        print(f"Failed to send Slack message: {str(e)}")
        print(f"Response: {e.response.text if e.response else 'No response'}")


def send_deleted_menus_message(menus: list):
    message = f"{len(menus)} menus deleted: \n" + build_body_message(menus)
    _send_slack_message(message)
    print(f"Menus deleted: {repr(menus)})")


def send_new_menus_message(menus: list):
    message = f"{len(menus)} new menus found: \n" + build_body_message(menus)
    _send_slack_message(message)
    print(f"New menus found: {repr(menus)})")


def send_edited_menus_message(menus: list):
    message = f"{len(menus)} menus edited: \n" + build_body_message(menus)
    _send_slack_message(message)
    print(f"Menus edited: {repr(menus)})")


def send_new_restaurants_message(restaurants: list):
    slack_message = f"{len(restaurants)} new restaurants found: \n" + build_body_message(restaurants)
    if restaurants:
        _send_slack_message(slack_message)
    print(f"New restaurants: {repr(restaurants)}")


def build_body_message(menus_or_restaurants: list):
    body_message = ""
    for i, menu_or_restaurant in enumerate(menus_or_restaurants):
        body_message += f'"{menu_or_restaurant.get("name_kr")}", '
        if i % 5 == 4:
            body_message += "\n"
    return body_message
