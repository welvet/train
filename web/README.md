# Train web UI

A minimal Next.js and TypeScript UI for the train project. The current page is
intentionally limited to “Hello world” and does not connect to the backend.

## Requirements

- Node.js 20.9 or newer
- npm

## Development

```sh
npm install
npm run dev
```

The development server is only for local iteration.

## Static build

```sh
npm ci
npm run build
```

Next.js writes the static site to `out/`. The release builder packages that
directory into the Python wheel, and the backend web API serves it from `/`.
A Node.js server is not required in production.

## Checks

```sh
npm run lint
npm run typecheck
```
