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
    let progress = []

    // Real-time Todo Interactions
    document.querySelector('.todo-list').addEventListener('click', async (e) => {
        const todoItem = e.target.closest('.todo-item');
        const todoId = todoItem?.dataset.todoId;

        // Checkbox Toggle
        if (e.target.matches('input[type="checkbox"]')) {
            const isCompleted = e.target.checked;
            const textElement = todoItem.querySelector('.todo-text');
            if (isCompleted){textElement.classList.add('completed')}
            else{textElement.classList.remove('completed')}
            let todoIndex = progress.findIndex(todo => todo.todoId === todoId);
            if (todoIndex !== -1){
                progress.splice(todoIndex, 1);
            }else{
                progress.push({ todoId, progress: isCompleted ? 1 : -1 })
            }
            if (progress.length !== 0){
                toggleProgressUI("show");
            }else{
                toggleProgressUI("hide")
            }
        }

        // Delete Todo
        if (e.target.closest('.btn-delete')) {
            if (progress.length !== 0){
                alert("You have unsaved changes, progress would be lost if you continue")
            }
            const wasCompleted = todoItem.dataset.initialCompleted === 'true';
            await deleteTodo(todoId, wasCompleted);
            location.reload();
        }

        // Edit Todo
        if (e.target.closest('.btn-edit')) {
            if (progress.length !== 0){
                alert("You have unsaved changes, progress would be lost if you continue")
            }
            const textElement = todoItem.querySelector('.todo-text');
            const newText = prompt('Edit todo:', textElement.textContent);
            if (newText) {
                await updateTodo(todoId, { content: newText });
                location.reload();
            }
        }
    });

    // Add New Todo
    document.getElementById('add-task-btn').addEventListener('click', async () => {
        const btn = document.getElementById('add-task-btn');
        btn.disabled = true;
        if (progress.length !== 0){
            alert("You have unsaved changes, progress would be lost if you continue")
        }
        const input = document.getElementById('task-input');
        const content = input.value.trim();
        if (!content) return;

        await fetch(`/tasks/${taskId}/todos`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken 
            },
            body: JSON.stringify({ content })
        });

        location.reload();
    });

    // Save Progress
    document.getElementById('save-progress').addEventListener('click', async () => {
        for (let index = 0; index < progress.length; index++) {
            const todo = progress[index];
            await updateTodo(todo.todoId, { is_completed: todo.progress === 1 ? true : false });            
        }
        progress = progress.map(todo => todo.progress)
        notes = document.getElementById("notes").value
        await fetch(`/tasks/${taskId}/progress`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ progress, notes: notes ? notes : null })
        });
        location.reload();
    });

    // Discard Changes
    document.getElementById('discard-progress').addEventListener('click', () => {
        document.querySelectorAll('.todo-item').forEach(item => {
            const checkbox = item.querySelector('input[type="checkbox"]');
            checkbox.checked = item.dataset.initialCompleted === 'true';
            const textElement = item.querySelector('.todo-text');
            if (checkbox.checked){textElement.classList.add('completed')}
            else{textElement.classList.remove('completed')}
        });
        progress = []
        toggleProgressUI("hide")
    });

    // Helper Functions
    function toggleProgressUI(action){
        if (action === "show"){
            document.querySelector('.progress-actions').classList.add('visible');
        }else{
            document.querySelector('.progress-actions').classList.remove('visible');
        }
    }

    // Helper function to update a todo
    async function updateTodo(todoId, data) {
        await fetch(`/todos/${todoId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken  
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
                'X-CSRFToken': csrfToken  
            }
        });
    }
});