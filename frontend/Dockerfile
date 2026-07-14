FROM node:22-alpine

WORKDIR /app

# Install dependencies first (for docker caching)
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source
COPY . .

# Expose Vite default dev port
EXPOSE 5173

# Run Vite in dev mode bound to all interfaces
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
