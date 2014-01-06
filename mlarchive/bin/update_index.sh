export PYTHONPATH=/a/mailarch/current
cd /a/mailarch/current
#./manage.py rebuild_index --noinput
./manage.py update_index --age=30
