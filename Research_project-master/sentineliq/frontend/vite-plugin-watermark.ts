import type { Plugin } from 'vite';

export const watermarkInjectPlugin = ({ logo, url, theme }: { logo: string; url: string; theme: string }) => {
    const watermarkContainerId = 'built_with_uptiq__attribution';

    const isDarkTheme = theme === 'dark';
    const backgroundColor = isDarkTheme ? '#111111' : '#fff';
    const textColor = isDarkTheme ? '#CECECE' : '#374151';

    const watermarkScript = `
    (function() {
      function createWatermark() {
        let wm = document.getElementById("${watermarkContainerId}");
        if (wm) return wm;

        wm = document.createElement("a");
        wm.href = "${url}";
        wm.target = "_blank";
        wm.rel = "noopener";
        wm.id = "${watermarkContainerId}";
        wm.style.position = "fixed";
        wm.style.textDecoration = "none";
        wm.style.overflow = "hidden";
        wm.style.right = "20px";
        wm.style.bottom = "20px";
        wm.style.zIndex = "999999";
        wm.style.height = "36px";
        wm.style.maxHeight = "36px";
        wm.style.backgroundColor = "${backgroundColor}";
        wm.style.borderRadius = "999px";
        wm.style.userSelect = "none";
        wm.style.display = "flex";
        wm.style.alignItems = "center";
        wm.style.justifyContent = "center";
        wm.style.gap = "5px";
        wm.style.fontFamily = "'Mulish', system-ui, sans-serif";
        wm.style.fontSize = "14px";
        wm.style.lineHeight = "20px";
        wm.style.color = "${textColor}";
        wm.style.paddingBlock = "8px";
        wm.style.paddingInline = "12px";
        wm.style.boxShadow = "0 0 25px -5px rgba(0, 0, 0, 0.10), 0 0 10px -5px rgba(0, 0, 0, 0.04)";

        var txtBuild = document.createElement("p");
        txtBuild.style.margin="0";
        txtBuild.style.padding="0";
        txtBuild.style.fontWeight="500";
        txtBuild.innerText = "Built with";

        var img = document.createElement("img");
        img.src = "${logo}";
        img.style.height = "16px";
        img.style.objectFit = "contain";
        img.style.flexShrink = "0";

        wm.appendChild(txtBuild);
        wm.appendChild(img);

        document.body.appendChild(wm);
      }

      // Create watermark initially
      createWatermark();

      // Observe DOM and re-create if removed
      const observer = new MutationObserver(() => {
        if (!document.getElementById("${watermarkContainerId}")) {
          createWatermark();
        }
      });

      observer.observe(document.body, { childList: true, subtree: true });
    })();
  `;

    return {
        name: 'vite-watermark-inject',
        transformIndexHtml: html => {
            if (!logo) return html;
            return {
                html,
                tags: [
                    {
                        tag: 'script',
                        children: watermarkScript,
                        injectTo: 'body'
                    }
                ]
            };
        }
    } as Plugin;
};
