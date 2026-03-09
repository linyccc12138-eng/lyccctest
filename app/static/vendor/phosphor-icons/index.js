var head = document.getElementsByTagName("head")[0];

// 加载本地 Phosphor Icons CSS 文件
for (const weight of ["regular", "thin", "light", "bold", "fill", "duotone"]) {
  var link = document.createElement("link");
  link.rel = "stylesheet";
  link.type = "text/css";
  link.href = `/static/vendor/phosphor-icons/${weight}/style.css`;
  head.appendChild(link);
}
