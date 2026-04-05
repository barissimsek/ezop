/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    turbopack: {
      paths: {
        "@/*": ["./*"],
      },
    },
  },
};

module.exports = nextConfig;
