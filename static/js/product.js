sizeOptions = document.querySelectorAll(".sizeTable > button");

sizeOptions.forEach(item => { 
  item.addEventListener('click', (event) => {
    const wasSelected = item.classList.contains('selectedSize');
    sizeOptions.forEach(item => {
      item.classList.remove('selectedSize');
      document.body.classList.remove('sizeSelected'); 
    });
    if (!wasSelected) {
      item.classList.add('selectedSize');
      document.body.classList.add('sizeSelected');
      // console.log('Size ' + item.textContent + ' was selected');
    }
  });
});