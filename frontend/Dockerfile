# Imagem de desenvolvimento: Vite com hot reload.
FROM node:24-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
EXPOSE 5180
CMD ["npm", "run", "dev"]
