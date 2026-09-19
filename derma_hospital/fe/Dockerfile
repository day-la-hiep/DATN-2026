# Build: docker build -f fe/Dockerfile -t derma-fe fe/  (context = fe/, tự chứa)
#
# KHÔNG dùng `output: "standalone"` (Next.js) — đã thử, gặp bug đã biết giữa Next.js
# file-tracing + pnpm virtual store (`.pnpm/...`): thiếu
# `@swc/helpers/esm/_interop_require_default.js` lúc chạy dù build thành công, thêm
# `@swc/helpers` làm dependency trực tiếp cũng không fix (next tự cần bản nested riêng
# trong `.pnpm` của chính nó). Copy nguyên `node_modules` production thay vì
# `.next/standalone` — image nặng hơn nhưng chắc chắn chạy đúng, không phụ thuộc
# file-tracer đoán đúng mọi transitive dependency.
FROM node:22-slim AS base
RUN corepack enable

FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# BACKEND_URL PHẢI có lúc BUILD: `rewrites()` trong next.config.ts được tính 1 lần khi
# `next build` rồi bake vào .next/routes-manifest.json — set env lúc runtime KHÔNG có tác
# dụng (đã dính: FE gọi ECONNREFUSED 127.0.0.1:3050). Truyền qua build arg (compose).
ARG BACKEND_URL=http://localhost:3050
ENV BACKEND_URL=$BACKEND_URL
RUN pnpm build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next

EXPOSE 3000
# Gọi thẳng binary `next` thay vì `pnpm start` — tránh corepack/pnpm tự chạy lại
# "deps status check" (tải pnpm từ npm registry + re-verify node_modules) mỗi lần
# container khởi động, vốn cần mạng ra ngoài và lặp lại đúng lỗi approve-builds
# (`pnpm-workspace.yaml` không có ở stage này) dù node_modules đã cài đúng từ lúc build.
CMD ["node_modules/.bin/next", "start", "-p", "3000"]
