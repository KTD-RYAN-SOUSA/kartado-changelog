# Lazy stuff here

use-local:
	rm .env
	echo "STAGE=LOCAL" > .env

use-staging:
	rm .env
	echo "STAGE=STAGING" > .env

use-homolog:
	rm .env
	echo "STAGE=HOMOLOG" > .env

use-pre-shared:
	rm .env
	echo "STAGE=PRE_SHARED" > .env

use-homolog-auscultacao:
	rm .env
	echo "STAGE=HOMOLOG_AUSCULTACAO" > .env

use-homolog-contratos:
	rm .env
	echo "STAGE=HOMOLOG_CONTRATOS" > .env

use-next:
	rm .env
	echo "STAGE=NEXT" > .env

use-production:
	rm .env
	echo "ATENTION! You are using the production database!"
	echo "STAGE=PRODUCTION" > .env

use-engie-staging:
	rm .env
	echo "ATENTION! You are using the ENGIE staging database!"
	echo "STAGE=ENGIE_STAGING" > .env

use-engie-production:
	rm .env
	echo "ATENTION! You are using the ENGIE production database!"
	echo "STAGE=ENGIE_PRODUCTION" > .env

use-ccr-homolog:
	rm .env
	echo "ATENTION! You are using the CCR homolog database!"
	echo "STAGE=CCR_HOMOLOG" > .env

use-ccr-production:
	rm .env
	echo "ATENTION! You are using the CCR production database!"
	echo "STAGE=CCR_PRODUCTION" > .env

use-homolog-monitoramentos:
	rm .env
	echo "STAGE=HOMOLOG_MONITORAMENTOS" > .env

deploy:
	rm .env
	echo "STAGE=STAGING" > .env
	python manage.py migrate
	zappa update staging
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-pre-shared:
	rm .env
	echo "STAGE=PRE_SHARED" > .env
	python manage.py migrate
	zappa update pre_shared
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-homolog-auscultacao:
	rm .env
	echo "STAGE=HOMOLOG_AUSCULTACAO" > .env
	python manage.py migrate
	zappa update homolog_contratos
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-homolog-contratos:
	rm .env
	echo "STAGE=HOMOLOG_CONTRATOS" > .env
	python manage.py migrate
	zappa update homolog_contratos
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-next:
	rm .env
	echo "STAGE=NEXT" > .env
	python manage.py migrate
	zappa update next
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-production:
	rm .env
	echo "STAGE=PRODUCTION" > .env
	python manage.py migrate
	python manage.py collectstatic --noinput
	zappa update production
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-engie-staging:
	rm .env
	echo "STAGE=ENGIE_STAGING" > .env
	python manage.py migrate
	python manage.py collectstatic --noinput
	zappa update engie_staging
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-engie-production:
	rm .env
	echo "STAGE=ENGIE_PRODUCTION" > .env
	python manage.py migrate
	python manage.py collectstatic --noinput
	zappa update engie_production
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-ccr-homolog:
	rm .env
	echo "STAGE=CCR_HOMOLOG" > .env
	python manage.py migrate
	python manage.py collectstatic --noinput
	zappa update ccr_homolog
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-ccr-production:
	rm .env
	echo "STAGE=CCR_PRODUCTION" > .env
	python manage.py migrate
	python manage.py collectstatic --noinput
	zappa update ccr_production
	rm .env
	echo "STAGE=LOCAL" > .env

deploy-homolog-monitoramentos:
	rm .env
	echo "STAGE=HOMOLOG_MONITORAMENTOS" > .env
	python manage.py migrate
	zappa update homolog_monitoramentos
	rm .env
	echo "STAGE=LOCAL" > .env
