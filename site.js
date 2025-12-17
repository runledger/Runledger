window.tailwind = window.tailwind || {};
window.tailwind.config = {
    theme: {
        extend: {
            colors: {
                bg: '#020408',
                card: '#0A0C12',
                border: '#1E2230',
                borderHover: '#30364A',
                primary: '#3B82F6',
                primaryGlow: 'rgba(59, 130, 246, 0.5)',
                accent: '#06B6D4',
                textMain: '#F8FAFC',
                textMuted: '#94A3B8',
                codeBg: '#0D1117',
                diffAdd: 'rgba(35, 134, 54, 0.15)',
                diffAddText: '#3FB950',
                diffDel: 'rgba(218, 54, 51, 0.15)',
                diffDelText: '#F85149'
            },
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
                mono: ['JetBrains Mono', 'monospace']
            },
            backgroundImage: {
                'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
                'hero-glow': 'conic-gradient(from 180deg at 50% 50%, #1E293B 0deg, #0F172A 180deg, #1E293B 360deg)'
            },
            animation: {
                'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                'float': 'float 6s ease-in-out infinite',
                'flow': 'flow 2s linear infinite',
                'flow-slow': 'flow 15s linear infinite',
                'fade-in': 'fadeIn 0.8s ease-out forwards',
                'grow-bar': 'growBar 2s ease-out infinite',
                'scroll-logs': 'scrollLogs 10s linear infinite',
                'stream': 'stream 1.5s linear infinite'
            },
            keyframes: {
                float: {
                    '0%, 100%': { transform: 'translateY(0)' },
                    '50%': { transform: 'translateY(-6px)' }
                },
                flow: {
                    '0%': { strokeDashoffset: '24' },
                    '100%': { strokeDashoffset: '0' }
                },
                stream: {
                    '0%': { backgroundPosition: '-100% 0' },
                    '100%': { backgroundPosition: '200% 0' }
                },
                fadeIn: {
                    '0%': { opacity: '0', transform: 'translateY(10px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' }
                },
                growBar: {
                    '0%': { width: '0%' },
                    '60%': { width: '85%' },
                    '100%': { width: '85%' }
                },
                scrollLogs: {
                    '0%': { transform: 'translateY(0)' },
                    '100%': { transform: 'translateY(-50%)' }
                }
            }
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('mobile-menu-btn');
    const menu = document.getElementById('mobile-menu');

    if (btn && menu) {
        btn.addEventListener('click', () => {
            menu.classList.toggle('hidden');
        });
    }

    if (window.lucide) {
        window.lucide.createIcons();
    }
});

window.addEventListener('load', () => {
    if (window.lucide) {
        window.lucide.createIcons();
    }
});
