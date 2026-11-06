import type { Plugin } from 'vite';

export const loaderInjectPlugin = (options?: {
    backgroundColor?: string;
    spinnerColor?: string;
    fadeOutDelay?: number;
}) => {
    const loaderContainerId = 'vite-loader';
    const backgroundColor = options?.backgroundColor || 'rgba(255, 255, 255, 0.9)';
    const fadeOutDelay = options?.fadeOutDelay || 100;

    const loaderStyles = `
        #${loaderContainerId} {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: ${backgroundColor};
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            transition: opacity 0.3s ease;
        }
        #${loaderContainerId}.hidden {
            opacity: 0;
            pointer-events: none;
        }
        #${loaderContainerId} .loader {
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            color: gray;
            stroke: gray;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    `;

    const loaderScript = `
        (() => {
            const createLoader = () => {
                let loader = document.getElementById("${loaderContainerId}");
                if (loader) return loader;

                loader = document.createElement("div");
                loader.id = "${loaderContainerId}";
                
                const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
                svg.setAttribute("class", "loader medium");
                svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
                svg.setAttribute("viewBox", "0 0 24 24");
                svg.setAttribute("fill", "none");
                svg.setAttribute("stroke", "currentColor");
                svg.setAttribute("stroke-width", "2");
                svg.setAttribute("stroke-linecap", "round");
                svg.setAttribute("stroke-linejoin", "round");
                
                const paths = [
                    { d: "M12 2v4" },
                    { d: "m16.2 7.8 2.9-2.9" },
                    { d: "M18 12h4" },
                    { d: "m16.2 16.2 2.9 2.9" },
                    { d: "M12 18v4" },
                    { d: "m4.9 19.1 2.9-2.9" },
                    { d: "M2 12h4" },
                    { d: "m4.9 4.9 2.9 2.9" }
                ];
                
                paths.forEach(pathData => {
                    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                    path.setAttribute("d", pathData.d);
                    svg.appendChild(path);
                });
                
                loader.appendChild(svg);
                document.body.appendChild(loader);
                
                return loader;
            }

            const removeLoader = () => {
                const loader = document.getElementById("${loaderContainerId}");
                if (loader) {
                    loader.classList.add('hidden');
                    setTimeout(() => {
                        if (loader.parentNode) {
                            loader.parentNode.removeChild(loader);
                        }
                    }, ${fadeOutDelay});
                }
            }

            // Create loader immediately
            if (document.body) {
                createLoader();
            } else {
                document.addEventListener('DOMContentLoaded', createLoader);
            }

            // Remove loader when page is fully loaded
            if (document.readyState === 'complete') {
                removeLoader();
            } else {
                window.addEventListener('load', removeLoader);
            }
        })()
    `;

    return {
        name: 'vite-loader-inject',
        transformIndexHtml: html => {
            return {
                html,
                tags: [
                    {
                        tag: 'style',
                        children: loaderStyles,
                        injectTo: 'head'
                    },
                    {
                        tag: 'script',
                        children: loaderScript,
                        injectTo: 'body'
                    }
                ]
            };
        }
    } as Plugin;
};
