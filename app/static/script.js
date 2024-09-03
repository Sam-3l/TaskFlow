function toggleMenu() {
    var menu = document.getElementById("userMenu");
    menu.classList.toggle("active");
}

document.addEventListener('click', function(event) { 
    var menu = document.getElementById("userMenu");
    var profileImg = document.querySelector('.profile-img');

    // If the click was outside the menu and not on the profile image, close the menu
    if (!menu.contains(event.target) && !profileImg.contains(event.target)) {
        menu.classList.remove("active");
    }
});

// Store the last known scroll position
let lastScrollTop = 0;
const navbar = document.querySelector('.nav-g');

window.addEventListener('scroll', function() {
    let currentScroll = window.pageYOffset || document.documentElement.scrollTop;

    if (currentScroll > lastScrollTop) {
        // Scrolling down
        navbar.style.top = '-70px'; // Adjust based on your navbar height
    } else {
        // Scrolling up
        navbar.style.top = '0';
    }

    lastScrollTop = currentScroll <= 0 ? 0 : currentScroll; // For Mobile or negative scrolling
});


function displayoff(element_id, input = null){
    let error_message = document.getElementById(element_id);
    error_message.style.display = "none";

    if (element_id == "uname_err"){
        var regex = /^[a-zA-Z0-9_]*$/;
            var errorMessage = document.getElementById('error-message');

            if (!regex.test(input.value)) {
                errorMessage.textContent = "Only alphanumeric characters and underscores are allowed.";
            } else {
                errorMessage.textContent = ""; // Clear error message if input is valid
            }
    }
}

function validateForm() {
    var input = document.getElementById('username');
    var regex = /^[a-zA-Z0-9_]*$/;
    var errorMessage = document.getElementById('error-message');

    if (!regex.test(input.value)) {
        errorMessage.textContent = "Only alphanumeric characters and underscores are allowed.";
        return false; // Prevent form submission
    }

    return true; // Allow form submission
}

function flash() {
        // Get the flash message element
        var flashMessage = document.getElementById('flash-message');

        // Show the flash message
        flashMessage.classList.add('show');

        // Automatically hide the flash message after 3 seconds
        setTimeout(function() {
            flashMessage.classList.remove('show');
        }, 3000);

        // Close button functionality
        var closeButton = document.getElementById('close-btn');
        closeButton.addEventListener('click', function() {
            flashMessage.classList.remove('show');
        });
    }

    document.addEventListener("DOMContentLoaded", function() {
        const navLinks = document.querySelectorAll('.navbar-dark .nav-link');
    
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                navLinks.forEach(nav => nav.classList.remove('active'));
                this.classList.add('active');
            });
        });
    });
    

document.addEventListener('DOMContentLoaded', function () {
    const fab = document.getElementById('fab');
    const fabOptions = document.getElementById('fab-options');

    fab.addEventListener('click', function () {
        fab.classList.toggle('open');
        fabOptions.style.display = fab.classList.contains('open') ? 'flex' : 'none';
    });

    document.addEventListener('click', function (event) {
        const isClickInside = fab.contains(event.target) || fabOptions.contains(event.target);

        if (!isClickInside) {
            fab.classList.remove('open');
            fabOptions.style.display = 'none';
        }
    });
});

document.addEventListener('DOMContentLoaded', function () {
  const addTaskBtn = document.getElementById('add-task-btn');
  const taskInput = document.getElementById('task-input');
  const todoList = document.querySelector('.todo-list');

  // Function to add a task
  addTaskBtn.addEventListener('click', function () {
    const taskText = taskInput.value.trim();
    if (taskText) {
      addTask(taskText);
      taskInput.value = '';
    }
  });

  // Add task to the list
  function addTask(taskText) {
    const listItem = document.createElement('li');
    listItem.className = 'list-group-item todo-item';

    // Checkbox for completion
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'form-check-input';
    checkbox.addEventListener('change', toggleComplete);

    // Task label
    const label = document.createElement('span');
    label.className = 'task-label';
    label.textContent = taskText;

    // Edit button
    const editBtn = document.createElement('button');
    editBtn.className = 'todo-btn btn btn-warning btn-sm';
    editBtn.textContent = 'Edit';
    editBtn.addEventListener('click', () => editTask(label));

    // Delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'todo-btn btn btn-danger btn-sm';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', () => listItem.remove());

    listItem.appendChild(checkbox);
    listItem.appendChild(label);
    listItem.appendChild(editBtn);
    listItem.appendChild(deleteBtn);
    todoList.appendChild(listItem);
  }

  // Toggle task completion
  function toggleComplete(event) {
    const label = event.target.nextSibling;
    if (event.target.checked) {
      label.classList.add('completed');
    } else {
      label.classList.remove('completed');
    }
  }

  // Edit task
  function editTask(label) {
    const newTaskText = prompt('Edit your task:', label.textContent);
    if (newTaskText !== null && newTaskText.trim() !== '') {
      label.textContent = newTaskText.trim();
    }
  }
});
