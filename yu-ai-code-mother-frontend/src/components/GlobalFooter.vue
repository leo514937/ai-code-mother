<template>
  <a-layout-footer class="footer">
    <div class="footer-content">
      <p class="copyright">
        <a
          href="https://www.codefather.cn"
          target="_blank"
          rel="noopener noreferrer"
          class="author-link"
        >
          编程导航原创项目 by 程序员鱼皮
        </a>
      </p>
    </div>
  </a-layout-footer>
</template>

<script setup lang="ts">
// 无需额外的响应式数据
</script>

<style scoped>
.footer {
  background: var(--surface-bg);
  backdrop-filter: blur(10px);
  text-align: center;
  padding: 20px;
  margin-top: 40px;
  border-top: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.copyright {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.author-link {
  color: var(--text-primary);
  text-decoration: none;
}

.author-link:hover {
  color: rgb(var(--brand-primary-rgb));
}
</style>
