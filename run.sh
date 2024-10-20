docker build -t $(dotenv -f .env get CR)/livewall:latest .
docker run --rm -it -p 3000:3000 --env-file .env $(dotenv -f .env get CR)/livewall:latest