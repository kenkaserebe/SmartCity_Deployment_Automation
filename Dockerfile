# Multi-stage build for optimized container
FROM node:18-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy application code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM node:18-alpine

# Install tini for proper signal handling
RUN apk add --no-cache tini

WORKDIR /app

# Copy built application
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package*.json ./

# Non-root user for security
USER node

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD node -e "require('http').get('http://localhost:3000/health', (r) => {r.statusCode === 200 ? process.exit(0) : process.exit(1)})"

ENTRYPOINT [ "/sbin/tini", "--" ]
CMD [ "node", "dist/index.js" ]