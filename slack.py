import requests
import os

def send_slack_message(msg):
    body = {
        'channel': os.environ['SLACK_CHANNEL'],
        'text': msg
    }
    headers = {'Authorization': f'Bearer {os.environ["SLACK_TOKEN"]}'}
    res = requests.post('https://slack.com/api/chat.postMessage', headers=headers, data=body)