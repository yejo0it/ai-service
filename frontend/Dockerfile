FROM node:20-alpine

WORKDIR /app

# package.json이 바뀔 때만 의존성을 다시 설치하도록 레이어를 분리한다.
COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 8002
# --host 0.0.0.0: 컨테이너 밖(호스트 브라우저)에서 접속할 수 있게 한다.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "8002"]
