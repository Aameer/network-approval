/** Proxy /api/* to the FastAPI backend so the console and API share an origin in dev. */
module.exports = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://localhost:8000/api/:path*" },
    ];
  },
};
