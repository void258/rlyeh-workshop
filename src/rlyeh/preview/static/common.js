// 审核页共用：地址带 ?embed 时（嵌在 Studio 里）给页面加上 embed 类，样式见 common.css
if (/[?&]embed(=|&|$)/.test(location.search)) document.documentElement.classList.add('embed')
