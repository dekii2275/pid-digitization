# Build the official pinned source; public prebuilt images may be unavailable.
FROM golang:1.24-alpine AS build
ENV CGO_ENABLED=0
RUN go install -trimpath github.com/minio/minio@RELEASE.2025-09-07T16-13-09Z

FROM alpine:3.21
RUN apk add --no-cache ca-certificates curl
COPY --from=build /go/bin/minio /usr/local/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
