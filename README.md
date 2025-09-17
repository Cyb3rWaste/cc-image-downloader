# cc-image-downloader
Download images from CSV &amp; Convert PNG to JPG

My first attempt at using GitHub and making something useful. 

It has a very niche use, and I would not recommend it to anyone else. 



Build from Git

docker build -t cc-image-downloader https://github.com/Cyb3rWaste/cc-image-downloader.git



docker run -d `
  --name cc-image-downloader `
  -p 5001:5000 `
  -v [LOCAL FOLDER TO MOUNT]:/app/downloads `
  -v [LOCAL FOLDER TO MOUNT]:/app/uploads `
  --restart unless-stopped `
  cc-image-downloader
