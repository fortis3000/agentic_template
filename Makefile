.PHONY: precommit install_dev_dependencies docker-build docker-run docker-up docker-down

# Install dev dependencies
install_dev_dependencies:
	uv sync --extra all

# Local precommit
precommit:
	bash ./precommit.sh

# Docker: build image from project root
docker-build:
	docker build -t ds-project -f docker/Dockerfile .

# Docker: run container interactively
docker-run:
	docker run --rm -it \
		-v $(PWD)/data:/app/data \
		-v $(PWD)/models:/app/models \
		-v $(PWD)/notebooks:/app/notebooks \
		ds-project

# Docker Compose: start services
docker-up:
	docker compose up --build -d

# Docker Compose: stop services
docker-down:
	docker compose down
