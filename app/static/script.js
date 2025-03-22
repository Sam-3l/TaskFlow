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


// Todos
document.addEventListener('DOMContentLoaded', function () {
    const addTaskBtn = document.getElementById('add-task-btn');
    const taskInput = document.getElementById('task-input');
    const todoList = document.querySelector('.todo-list');
    const saveProgressSection = document.querySelector('.save-progress');
    const saveProgressBtn = document.getElementById('save-progress-btn');
    const discardProgressBtn = document.getElementById('discard-progress-btn');

    let progressChanged = false;

    // Add Todo
    addTaskBtn.addEventListener('click', async function () {
        const taskText = taskInput.value.trim();
        if (taskText) {
            const response = await fetch(`/dashboard/tasks/${taskId}/add_todo`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: taskText })
            });
            const todo = await response.json();
            addTaskToDOM(todo);
            taskInput.value = '';
        }
    });

    // Toggle Todo Completion
    todoList.addEventListener('change', function (e) {
        if (e.target.classList.contains('form-check-input')) {
            const todoId = e.target.closest('.todo-item').dataset.todoId;
            const isCompleted = e.target.checked;
            fetch(`/dashboard/tasks/${taskId}/update_todo/${todoId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_completed: isCompleted })
            });
            progressChanged = true;
            saveProgressSection.classList.remove('d-none');
        }
    });

    // Save Progress
    saveProgressBtn.addEventListener('click', async function () {
        const response = await fetch(`/dashboard/tasks/${taskId}/save_progress`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ progress: calculateProgress() })
        });
        if (response.ok) {
            progressChanged = false;
            saveProgressSection.classList.add('d-none');
        }
    });

    // Discard Progress
    discardProgressBtn.addEventListener('click', function () {
        progressChanged = false;
        saveProgressSection.classList.add('d-none');
        location.reload(); // Reset UI to saved state
    });

    // Helper Functions
    function addTaskToDOM(todo) {
        const listItem = document.createElement('li');
        listItem.className = 'list-group-item todo-item d-flex align-items-center';
        listItem.dataset.todoId = todo.id;

        listItem.innerHTML = `
            <input type="checkbox" class="form-check-input me-3" ${todo.is_completed ? 'checked' : ''} />
            <span class="task-label flex-grow-1 ${todo.is_completed ? 'completed' : ''}">${todo.content}</span>
            <button class="btn btn-sm btn-warning me-2 edit-btn">Edit</button>
            <button class="btn btn-sm btn-danger delete-btn">Delete</button>
        `;
        todoList.appendChild(listItem);
    }

    function calculateProgress() {
        const completed = document.querySelectorAll('.form-check-input:checked').length;
        const total = document.querySelectorAll('.form-check-input').length;
        return completed - (total - completed); // +n for completed, -n for unchecked
    }
});