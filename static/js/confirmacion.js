document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("modal-confirmar");
  if (!modal) return;

  const texto = document.getElementById("modal-texto");
  const btnSi = document.getElementById("modal-si");
  const btnNo = document.getElementById("modal-no");
  let destino = null;

  document.querySelectorAll("[data-adoptar]").forEach((btn) => {
    btn.addEventListener("click", () => {
      destino = btn.dataset.url;
      texto.textContent = `¿Estás seguro de que quieres adoptar a ${btn.dataset.nombre}?`;
      modal.classList.remove("oculto");
    });
  });

  btnNo.addEventListener("click", () => modal.classList.add("oculto"));
  btnSi.addEventListener("click", () => {
    window.location.href = destino;
  });

  // Cerrar al tocar el fondo oscuro
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.add("oculto");
  });
});