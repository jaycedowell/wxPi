#!/bin/bash

tag=`date +"%Y%m%d-%H%M%S"`
sqlite3 wx-data.db ".backup 'wx-${tag}.db.bak'"
