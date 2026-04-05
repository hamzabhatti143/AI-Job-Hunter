/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'https://hamzabhatti-job-hunter.hf.space/:path*',
      },
    ]
  },
}
module.exports = nextConfig
