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

// Todos
document.addEventListener('DOMContentLoaded', () => {
    const taskId = document.getElementById('task-id').value;
    const csrfToken = document.getElementById('csrf-token').value; // Get CSRF token
    let isProgressModified = false;

    // Real-time Todo Interactions
    document.querySelector('.todo-list').addEventListener('click', async (e) => {
        const todoItem = e.target.closest('.todo-item');
        const todoId = todoItem?.dataset.todoId;

        // Checkbox Toggle
        if (e.target.matches('input[type="checkbox"]')) {
            const isCompleted = e.target.checked;
            await updateTodo(todoId, { is_completed: isCompleted });
            toggleProgressUI();
        }

        // Delete Todo
        if (e.target.closest('.btn-delete')) {
            const wasCompleted = todoItem.dataset.initialCompleted === 'true';
            await deleteTodo(todoId, wasCompleted);
            todoItem.remove();
            toggleProgressUI();
        }

        // Edit Todo
        if (e.target.closest('.btn-edit')) {
            const textElement = todoItem.querySelector('.todo-text');
            const newText = prompt('Edit todo:', textElement.textContent);
            if (newText) {
                await updateTodo(todoId, { content: newText });
                textElement.textContent = newText;
            }
        }
    });

    // Add New Todo
    document.getElementById('add-task-btn').addEventListener('click', async () => {
        const input = document.getElementById('task-input');
        const content = input.value.trim();
        if (!content) return;

        const todo = await fetch(`/tasks/${taskId}/todos`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken // Include CSRF token
            },
            body: JSON.stringify({ content })
        }).then(res => res.json());

        appendTodoItem(todo);
        input.value = '';
    });

    // Save Progress
    document.getElementById('save-progress').addEventListener('click', async () => {
        const progress = calculateCurrentProgress();
        await fetch(`/tasks/${taskId}/progress`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken // Include CSRF token
            },
            body: JSON.stringify({ progress })
        });
        isProgressModified = false;
        updateProgressUI();
    });

    // Discard Changes
    document.getElementById('discard-progress').addEventListener('click', () => {
        document.querySelectorAll('.todo-item').forEach(item => {
            const checkbox = item.querySelector('input[type="checkbox"]');
            checkbox.checked = item.dataset.initialCompleted === 'true';
        });
        isProgressModified = false;
        updateProgressUI();
    });

    // Helper Functions
    function toggleProgressUI() {
        isProgressModified = true;
        document.querySelector('.progress-actions').classList.add('visible');
    }

    function calculateCurrentProgress() {
        const changes = [];
        document.querySelectorAll('.todo-item').forEach(item => {
            const initial = item.dataset.initialCompleted === 'true';
            const current = item.querySelector('input').checked;
            if (initial !== current) changes.push(current ? 1 : -1);
        });
        return changes.reduce((a, b) => a + b, 0);
    }

    function appendTodoItem(todo) {
        const html = `
            <li class="todo-item" data-todo-id="${todo.id}" data-initial-completed="false">
                <label class="todo-checkbox">
                    <input type="checkbox" ${todo.is_completed ? 'checked' : ''} />
                    <span class="checkmark"></span>
                </label>
                <span class="todo-text">${todo.content}</span>
                <div class="todo-actions">
                    <button class="btn-edit"><i class="fas fa-pencil-alt"></i></button>
                    <button class="btn-delete"><i class="fas fa-trash"></i></button>
                </div>
            </li>
        `;
        document.querySelector('.todo-list').insertAdjacentHTML('beforeend', html);
    }

    // Helper function to update a todo
    async function updateTodo(todoId, data) {
        await fetch(`/todos/${todoId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken // Include CSRF token
            },
            body: JSON.stringify(data)
        });
    }

    // Helper function to delete a todo
    async function deleteTodo(todoId, wasCompleted) {
        await fetch(`/todos/${todoId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken // Include CSRF token
            }
        });
    }
});