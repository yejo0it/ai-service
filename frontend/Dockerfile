FROM node:20-alpine

WORKDIR /app

# package.json이 바뀔 때만 의존성을 다시 설치하도록 레이어를 분리한다.
COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 8002
# 시작할 때마다 의존성을 맞춘다. docker-compose의 node_modules 익명 볼륨은 컨테이너를
# 다시 만들어도 유지되므로, package.json이 바뀐 뒤 이미지만 재빌드하면 예전 패키지가 남는다.
# 이미 최신이면 1초 안에 끝나고, --no-save로 바인드 마운트된 package-lock.json은 건드리지 않는다.
# --host 0.0.0.0: 컨테이너 밖(호스트 브라우저)에서 접속할 수 있게 한다.
CMD ["sh", "-c", "npm install --no-save --no-audit --no-fund && npm run dev -- --host 0.0.0.0 --port 8002"]
