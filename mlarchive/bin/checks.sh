#!/bin/bash

echo "Directories / Files not group = www"
find /a/mailarch/data/archive ! -group www -print
