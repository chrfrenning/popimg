#!/bin/bash

# File to be uploaded
FILES=("image1.jpg" "image2.jpg")
FILE=${FILES[$RANDOM % ${#FILES[@]}]}

# URL to upload the file to
URL="http://localhost:3000/test"

# Use curl to upload the file as binary data with content type image/jpeg
curl -X PUT --data-binary @"${FILE}" -H "Content-Type: image/jpeg" "${URL}"
echo "See the uploaded file at ${URL}"