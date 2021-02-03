# SIKSHA CRAWLER

## Functionality
* 식당과 메뉴들에 대한 정보를 정기적으로(새벽 5시) 크롤링하고 RDS siksha DB 에 반영
* 크롤링 결과를 #siksha-noti 채널로 전송

## Deploy & Test([참고자료](https://www.serverless.com/blog/serverless-python-packaging/))
1. setting
    1. docker 설치 & 실행
    1. aws cli 설치 & configure 설정
    1. node & npm 설치([반드시 node 버전 14 이하로 유지](https://github.com/serverless/serverless/issues/8794))
    1. sudo npm install -g serverless
    1. npm init -y
    1. npm install --save serverless-python-requirements
    1. export SLS_DEBUG=*
    1. serverless config credentials --overwrite --provider aws --key <키 정보 입력> --secret <시크릿 키 정보 입력>
    1. serverless.yml 의 dockerizePip 설정을 주석을 참고하여 운영체제에 맞게 변경
1. deploy
    * serverless deploy
1. test
    * serverless invoke -f crawler --log

## Dependency Management
* requirements.txt
