# Imagem de desenvolvimento: Vite com hot reload.
FROM public.ecr.aws/docker/library/node:24.22.0-alpine3.24
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
EXPOSE 5180
CMD ["npm", "run", "dev"]
