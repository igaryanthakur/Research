FROM node:22.17.0-alpine
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack install --global pnpm@10.25.0
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

RUN apk add --no-cache openssl
RUN apk add --no-cache git
RUN apk add --no-cache rsync

# Create group and modify existing node user to match Kubernetes security context
RUN addgroup -g 3000 appgroup && \
    adduser node appgroup

# Increase file watcher limit
RUN echo fs.inotify.max_user_watches=524288 | tee -a /etc/sysctl.conf

COPY entrypoint.preview.sh /entrypoint.preview.sh
RUN chmod +x /entrypoint.preview.sh

# Switch to non-root user
USER node

WORKDIR /app/project

COPY package.json .
COPY pnpm-lock.yaml .
RUN pnpm install

EXPOSE 3000

ENTRYPOINT ["/entrypoint.preview.sh"]

