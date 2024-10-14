docker build -t $(dotenv -f .env get CR)/popimg:latest .
docker run --rm -it -p 3000:3000 $(dotenv -f .env get CR)/popimg:latest