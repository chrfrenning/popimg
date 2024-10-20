CR=$(dotenv -f .env get CR)
CRU=$(dotenv -f .env get CRU)
CRP=$(dotenv -f .env get CRP)
TAG=latest

docker build -t $(dotenv -f .env get CR)/livewall:$TAG .
docker login $CR -u $CRU -p $CRP
docker push $CR/livewall:$TAG