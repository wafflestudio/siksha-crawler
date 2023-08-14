# SIKSHA CRAWLER

## Dev Guidelines

- GitHub Flow + Issue based branch 방식을 사용합니다.
  - GitHub Flow는 [여기](https://medium.com/@patrickporto/4-branching-workflows-for-git-30d0aaee7bf) 참고
  - 개발이 필요한 사항은 우선 issue에 올리고, 해당 issue 번호로 branch를 만듭니다.
  - 예시 브랜치) feat/14-crawling-debugging
  - branch는 master에 머지 후 자동 삭제됩니다.
- Severless deploy는 master 머지 이전에 진행되어야 합니다.

  - master는 언제든 배포에 결함이 없는 상태여야 합니다.
  - **branch에서 작업 완료 -> PR -> review가 완료 -> sls deploy -> 이상 없는지 확인 -> merge**

- python formatter로 black을, linter로 pylint를 사용합니다.

## Functionality

- 식당과 메뉴들에 대한 정보를 정기적으로(새벽 5시) 크롤링하고 RDS siksha DB 에 반영
- 크롤링 결과를 #siksha-noti 채널로 전송

## Deploy & Test([참고자료](https://www.serverless.com/blog/serverless-python-packaging/))

1. setting
   1. docker 설치 & 실행
   1. aws cli 설치 & configure 설정
   1. node & npm 설치([반드시 node 버전 14 이하로 유지](https://github.com/serverless/serverless/issues/8794))
   1. sudo npm install -g serverless
   1. npm init -y
   1. npm install --save serverless-python-requirements
   1. export SLS_DEBUG=\*
   1. serverless config credentials --overwrite --provider aws --key <키 정보 입력> --secret <시크릿 키 정보 입력>
   1. serverless.yml 의 dockerizePip 설정을 주석을 참고하여 운영체제에 맞게 변경
1. deploy
   - serverless deploy
1. test
   - serverless invoke -f crawler --log

## Dependency Management

- requirements.txt

## Crawler Debugging

```
$ python3 handler.py --restaurant {식당이름(일부)} --date 20221014
```

> --restaurant (-r) 인자는 필수 <br>
> --date (-d) 인자는 옵션. 연월일(20221106) 형식으로 date를 넣으면 그 날 식단만 나오고, 안쓰면 긁은거 다 나옴.

- 주의) 크롤링 코드는 동일, 단순히 필터링해주는 방식임. 남용하면 서버에 부하줄 수 있음.
- 주의) 예외처리 되어있지 않음. argument 잘못 줄 경우 에러 발생 가능성
<<<<<<< Updated upstream
=======

### Docker Build Test
로컬에서 빌드가 잘 되는지 테스트하고 싶다면, 아래와 같이 실행합니다. ([GitHub Workflow](.github/workflows/ecr-dev.yml) 참고)
```shell 
docker build -t {이미지이름} --build-arg {KEY}={VALUE} 
```

## Deployment

1. dev, prod 브랜치에 push시 깃헙 액션을 통해 ECR에 이미지 푸시됩니다.
1. ECR에 이미지 태그 변화를 aws lambda에서 감지하여 waffle-world 레포의 이미지 버전이 업데이트
1. Kubernetes 크론잡이 정해진 스케줄에 따라 식당 크롤링을 실행합니다.

- 20230815 db 이전 (maria -> mysql)
>>>>>>> Stashed changes
