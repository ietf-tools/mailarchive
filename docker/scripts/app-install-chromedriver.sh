#!/bin/bash

HOSTARCH=$(arch)
if [ $HOSTARCH == "x86_64" ]; then
    DRIVERPATH=linux64/chromedriver-linux64.zip
    DRIVERSUBDIR=chromedriver-linux64
elif [ $HOSTARCH == "arm64" ] || [ $HOSTARCH == "aarch64" ]; then
    DRIVERPATH=mac-arm64/chromedriver-mac-arm64.zip
    DRIVERSUBDIR=chromedriver-mac-arm64
else
    echo $HOSTARCH
    echo "This architecture doesn't support chromedriver. Skipping installation..."
    exit 1
fi

echo "Installing chrome driver..."
wget -q --continue -P /chromedriver "https://storage.googleapis.com/chrome-for-testing-public/$CHROMEDRIVER_VERSION/$DRIVERPATH"
unzip /chromedriver/chromedriver* -d /chromedriver
ln -s /chromedriver/$DRIVERSUBDIR/chromedriver /usr/local/bin/chromedriver
ln -s /chromedriver/$DRIVERSUBDIR/chromedriver /usr/bin/chromedriver