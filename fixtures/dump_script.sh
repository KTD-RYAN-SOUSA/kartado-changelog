echo '%load_ext autoreload \n %autoreload 2 \n from fixtures.dump_steps import step_one \n step_one()' | python manage.py shell_plus
echo '%load_ext autoreload \n %autoreload 2 \n from fixtures.dump_steps import step_two \n step_two()' | python manage.py shell_plus
echo '%load_ext autoreload \n %autoreload 2 \n from fixtures.dump_steps import step_three \n step_three()' | python manage.py shell_plus
