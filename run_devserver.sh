#!/bin/bash
cd ../../../
TARGET_PATH=dotorg/gongo/appengine_cap2kml
blaze build ${TARGET_PATH}:local
dev_appserver.py blaze-bin/$TARGET_PATH/bundle-local -a 0.0.0.0 -p 9100
