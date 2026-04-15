# Run with VERSION env variable set; e.g. make push-image -e VERSION=$(git rev-parse --short HEAD)
# Note that makefiles differentiate between tabs and spaces in a weird way!

# Ensure VERSION is set.
ifndef VERSION
$(error VERSION variable is not set. Use -e VERSION=XYZ to proceed.)
endif

.PHONY: build-image push-image

REPO ?= freelawproject/courtlistener-mcp
DOCKER_TAG_PROD = $(VERSION)-prod
UNAME := $(shell uname -m)

build-image:
	docker build -t $(REPO):$(DOCKER_TAG_PROD) --build-arg TARGET_ENV=prod --build-arg GIT_SHA=$(VERSION) --file Dockerfile .

push-image: build-image
	$(info Checking if valid architecture)
	@if [ $(UNAME) != "x86_64" ]; then \
		echo "Only amd64 machines can push single-architecture builds. This \
protects against arm64 builds being accidentally deployed to the server (which uses amd64)."; \
		exit 1; \
	fi

	    echo "Architecture is OK. Pushing."; \
	    docker push $(REPO):$(DOCKER_TAG_PROD);
