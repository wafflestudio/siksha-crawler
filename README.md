# SIKSHA CRAWLER

## Dev Guidelines

- GitHub Flow + Issue based branch 방식을 사용합니다.
  - GitHub Flow는 [여기](https://medium.com/@patrickporto/4-branching-workflows-for-git-30d0aaee7bf) 참고
  - 개발이 필요한 사항은 우선 issue에 올리고, 해당 issue 번호로 branch를 만듭니다.
  - 예시 브랜치) feat/14-crawling-debugging
  - new PR -> dev 브랜치로 merge -> dev 브랜치가 테스트 통과하면 prod 브랜치로 merge

- python formatter로 black을, linter로 pylint를 사용합니다.

## Functionality

- 식당과 메뉴들에 대한 정보를 정기적으로(새벽 5시) 크롤링하고 RDS siksha DB 에 반영
- 크롤링 결과를 #siksha-noti 채널로 전송

## Deploy & Test
### Deploy

1. dev, prod 브랜치에 push시 깃헙 액션을 통해 ECR에 이미지 푸시됩니다.
1. ECR에 이미지 태그 변화를 aws lambda에서 감지하여 waffle-world 레포의 이미지 버전이 업데이트
1. Kubernetes 크론잡이 정해진 스케줄에 따라 식당 크롤링을 실행합니다.

### Test
로컬에서 빌드가 잘 되는지 테스트하고 싶다면, 아래와 같이 실행합니다.
- 이미지 빌드 테스트([github workflow](.github/workflows/ecr-dev.yml) 참고)
```shell 
$ docker build -t {이미지이름} --build-arg {KEY}={VALUE} 
```

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
