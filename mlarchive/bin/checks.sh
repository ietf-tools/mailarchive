#!/bin/bash

echo "Directories / Files not group = www"
find /a/mailarch/data/archive ! -group www -print

echo "List directories without GUID set"
find /a/mailarch/data/archive -maxdepth 1 ! -perm -g+s -exec ls -ld {} \;

echo "Other permission problems"
find /a/mailarch/data/archive -maxdepth 1 ! -perm -777 -exec ls -ld {} \;

