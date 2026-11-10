export function debounce(fn, wait) {
    let timer = null
    const run = (...args) => {
        clearTimeout(timer)
        timer = setTimeout(() => {
            timer = null
            fn(...args)
        }, wait)
    }
    run.cancel = () => {
        clearTimeout(timer)
        timer = null
    }
    return run
}