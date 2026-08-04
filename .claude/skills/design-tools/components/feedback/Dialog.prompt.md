Centered modal on a warm scrim. Reserve for decisions that block work (export, delete, share).

```jsx
<Dialog title="Export memo" description="Choose a format." onClose={close}
  footer={<><Button variant="secondary" onClick={close}>Cancel</Button><Button>Export</Button></>} />
```
