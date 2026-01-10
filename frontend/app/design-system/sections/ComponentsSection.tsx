'use client';

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from '@/components/ui/breadcrumb';
import { Separator } from '@/components/ui/separator';
import { 
  AlertCircle, 
  CheckCircle, 
  Info, 
  AlertTriangle, 
  Loader2,
  Mail,
  Search,
  User,
  Settings,
  LogOut,
  ChevronDown,
  Menu,
  Home,
  MoreHorizontal,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

export function ComponentsSection() {
  const [isLoading, setIsLoading] = useState(false);
  const [checked, setChecked] = useState(false);
  const [switchOn, setSwitchOn] = useState(false);
  const [radioValue, setRadioValue] = useState('option1');
  const [selectValue, setSelectValue] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const totalPages = 5;

  return (
    <section id="components" className="space-y-12">
      <div>
        <h2 className="text-3xl font-bold text-foreground mb-2">Components</h2>
        <p className="text-muted-foreground">
          Catálogo completo de componentes reutilizáveis
        </p>
      </div>

      {/* Buttons */}
      <div id="buttons" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Buttons</h3>
        
        {/* Variants */}
        <div className="space-y-4">
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Variants</h4>
            <div className="flex flex-wrap gap-3">
              <Button variant="default">Primary</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="outline">Outline</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="destructive">Destructive</Button>
              <Button variant="link">Link</Button>
            </div>
          </div>

          {/* Sizes */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Sizes</h4>
            <div className="flex flex-wrap items-center gap-3">
              <Button size="sm">Small</Button>
              <Button size="default">Default</Button>
              <Button size="lg">Large</Button>
              <Button size="icon">
                <Mail className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* States */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">States</h4>
            <div className="flex flex-wrap gap-3">
              <Button>Default</Button>
              <Button disabled>Disabled</Button>
              <Button disabled>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Inputs */}
      <div id="inputs" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Inputs</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Text Input</label>
            <Input type="text" placeholder="Enter text..." />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Email</label>
            <Input type="email" placeholder="email@example.com" />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Password</label>
            <Input type="password" placeholder="••••••••" />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Search</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input type="search" placeholder="Search..." className="pl-10" />
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Disabled</label>
            <Input type="text" placeholder="Disabled" disabled />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Read-only</label>
            <Input type="text" value="Read-only value" readOnly />
          </div>
        </div>
      </div>

      {/* Selectors */}
      <div id="selectors" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Selectors</h3>
        <div className="space-y-6 max-w-2xl">
          {/* Checkbox */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Checkbox</h4>
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <Checkbox 
                  id="checkbox1" 
                  checked={checked}
                  onCheckedChange={(checked) => setChecked(checked as boolean)}
                />
                <label htmlFor="checkbox1" className="text-sm font-medium text-foreground cursor-pointer">
                  Checkbox
                </label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox id="checkbox2" disabled />
                <label htmlFor="checkbox2" className="text-sm font-medium text-muted-foreground">
                  Disabled
                </label>
              </div>
            </div>
          </div>

          {/* Radio Group */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Radio Group</h4>
            <RadioGroup value={radioValue} onValueChange={setRadioValue}>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="option1" id="option1" />
                <Label htmlFor="option1">Option 1</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="option2" id="option2" />
                <Label htmlFor="option2">Option 2</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="option3" id="option3" disabled />
                <Label htmlFor="option3" className="text-muted-foreground">Option 3 (Disabled)</Label>
              </div>
            </RadioGroup>
          </div>

          {/* Switch */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Switch</h4>
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <Switch 
                  id="switch1" 
                  checked={switchOn}
                  onCheckedChange={setSwitchOn}
                />
                <label htmlFor="switch1" className="text-sm font-medium text-foreground cursor-pointer">
                  Switch {switchOn ? 'On' : 'Off'}
                </label>
              </div>
              <div className="flex items-center space-x-2">
                <Switch id="switch2" disabled />
                <label htmlFor="switch2" className="text-sm font-medium text-muted-foreground">
                  Disabled
                </label>
              </div>
            </div>
          </div>

          {/* Select */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Select</h4>
            <Select value={selectValue} onValueChange={setSelectValue}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select an option" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="option1">Option 1</SelectItem>
                <SelectItem value="option2">Option 2</SelectItem>
                <SelectItem value="option3">Option 3</SelectItem>
                <SelectItem value="option4">Option 4</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Badges */}
      <div id="badges" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Badges</h3>
        <div className="flex flex-wrap gap-3">
          <Badge variant="default">Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="outline">Outline</Badge>
          <Badge variant="destructive">Destructive</Badge>
        </div>
      </div>

      {/* Navigation */}
      <div id="navigation" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Navigation</h3>
        
        {/* Breadcrumb */}
        <div>
          <h4 className="text-lg font-medium text-foreground mb-3">Breadcrumb</h4>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">
                  <Home className="h-4 w-4" />
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/domains">Domains</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Domain Details</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </div>

        {/* Tabs */}
        <div>
          <h4 className="text-lg font-medium text-foreground mb-3">Tabs</h4>
          <div className="max-w-2xl">
            <Tabs defaultValue="tab1">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="tab1">Tab 1</TabsTrigger>
                <TabsTrigger value="tab2">Tab 2</TabsTrigger>
                <TabsTrigger value="tab3">Tab 3</TabsTrigger>
              </TabsList>
              <TabsContent value="tab1" className="border border-border rounded-lg p-4 mt-4">
                <p className="text-sm text-muted-foreground">Content for Tab 1</p>
              </TabsContent>
              <TabsContent value="tab2" className="border border-border rounded-lg p-4 mt-4">
                <p className="text-sm text-muted-foreground">Content for Tab 2</p>
              </TabsContent>
              <TabsContent value="tab3" className="border border-border rounded-lg p-4 mt-4">
                <p className="text-sm text-muted-foreground">Content for Tab 3</p>
              </TabsContent>
            </Tabs>
          </div>
        </div>

        {/* Pagination */}
        <div>
          <h4 className="text-lg font-medium text-foreground mb-3">Pagination</h4>
          <div className="flex items-center justify-center gap-2">
            <Button 
              variant="outline" 
              size="icon"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            {[...Array(totalPages)].map((_, i) => (
              <Button
                key={i + 1}
                variant={currentPage === i + 1 ? 'default' : 'outline'}
                size="icon"
                onClick={() => setCurrentPage(i + 1)}
              >
                {i + 1}
              </Button>
            ))}
            <Button 
              variant="outline" 
              size="icon"
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Cards */}
      <div id="cards" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Cards</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Card className="p-6">
            <h4 className="font-semibold text-foreground mb-2">Base Card</h4>
            <p className="text-sm text-muted-foreground">
              Card básico com padding e borda padrão
            </p>
          </Card>
          <Card className="p-6">
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-semibold text-foreground">Metric Card</h4>
              <CheckCircle className="h-5 w-5 text-success" />
            </div>
            <p className="text-3xl font-bold text-foreground">1,234</p>
            <p className="text-sm text-muted-foreground mt-1">Total domains</p>
          </Card>
          <Card className="p-6 bg-success/10 border-success">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="h-5 w-5 text-success" />
              <h4 className="font-semibold text-foreground">Status Card</h4>
            </div>
            <p className="text-sm text-muted-foreground">
              Sistema operando normalmente
            </p>
          </Card>
        </div>
      </div>

      {/* Tables */}
      <div id="tables" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Tables</h3>
        <div className="space-y-4">
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Default Table</h4>
            <div className="border border-border rounded-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Domain</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>SSL</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell className="font-medium">example.com</TableCell>
                    <TableCell>
                      <Badge variant="default" className="bg-success">Active</Badge>
                    </TableCell>
                    <TableCell>
                      <CheckCircle className="h-4 w-4 text-success" />
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem>View Details</DropdownMenuItem>
                          <DropdownMenuItem>Edit</DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem className="text-destructive">Delete</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">test.com</TableCell>
                    <TableCell>
                      <Badge variant="outline">Pending</Badge>
                    </TableCell>
                    <TableCell>
                      <AlertTriangle className="h-4 w-4 text-warning" />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">demo.com</TableCell>
                    <TableCell>
                      <Badge variant="destructive">Error</Badge>
                    </TableCell>
                    <TableCell>
                      <AlertCircle className="h-4 w-4 text-destructive" />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </div>

          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Loading State</h4>
            <Card className="p-6">
              <div className="space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            </Card>
          </div>

          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Empty State</h4>
            <Card className="p-12 text-center">
              <div className="mx-auto w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
                <Search className="h-8 w-8 text-muted-foreground" />
              </div>
              <h4 className="text-lg font-semibold text-foreground mb-2">No data</h4>
              <p className="text-sm text-muted-foreground">No records found in the table</p>
            </Card>
          </div>
        </div>
      </div>

      {/* Overlays */}
      <div id="overlays" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Overlays</h3>
        <div className="space-y-6">
          {/* Dialog */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Dialog / Modal</h4>
            <Dialog>
              <DialogTrigger asChild>
                <Button>Open Dialog</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Dialog Title</DialogTitle>
                  <DialogDescription>
                    This is a dialog description. It provides additional context about the dialog content.
                  </DialogDescription>
                </DialogHeader>
                <div className="py-4">
                  <p className="text-sm text-muted-foreground">Dialog content goes here.</p>
                </div>
                <DialogFooter>
                  <Button variant="outline">Cancel</Button>
                  <Button>Confirm</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          {/* Dropdown Menu */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Dropdown Menu</h4>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline">
                  Open Menu
                  <ChevronDown className="ml-2 h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuLabel>My Account</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem>
                  <User className="mr-2 h-4 w-4" />
                  Profile
                </DropdownMenuItem>
                <DropdownMenuItem>
                  <Settings className="mr-2 h-4 w-4" />
                  Settings
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-destructive">
                  <LogOut className="mr-2 h-4 w-4" />
                  Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Popover */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Popover</h4>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline">Open Popover</Button>
              </PopoverTrigger>
              <PopoverContent className="w-80">
                <div className="space-y-2">
                  <h4 className="font-medium text-foreground">Popover Title</h4>
                  <p className="text-sm text-muted-foreground">
                    This is a popover with some content inside.
                  </p>
                </div>
              </PopoverContent>
            </Popover>
          </div>

          {/* Tooltip */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Tooltip</h4>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="outline">Hover me</Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>This is a tooltip</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>
      </div>

      {/* User & Access */}
      <div id="user-access" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">User & Access</h3>
        <div className="space-y-6">
          {/* Avatar */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Avatar</h4>
            <div className="flex items-center gap-4">
              <Avatar>
                <AvatarImage src="https://github.com/shadcn.png" alt="User" />
                <AvatarFallback>JD</AvatarFallback>
              </Avatar>
              <Avatar>
                <AvatarFallback>AB</AvatarFallback>
              </Avatar>
              <Avatar className="h-12 w-12">
                <AvatarFallback>LG</AvatarFallback>
              </Avatar>
            </div>
          </div>

          {/* User Menu */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">User Menu</h4>
            <Card className="p-4 max-w-xs">
              <div className="flex items-center gap-3">
                <Avatar>
                  <AvatarFallback>JD</AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <p className="text-sm font-medium text-foreground">John Doe</p>
                  <p className="text-xs text-muted-foreground">john@example.com</p>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <Menu className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem>Profile</DropdownMenuItem>
                    <DropdownMenuItem>Settings</DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem className="text-destructive">Logout</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </Card>
          </div>

          {/* Role Badge */}
          <div>
            <h4 className="text-lg font-medium text-foreground mb-3">Role Badges</h4>
            <div className="flex flex-wrap gap-2">
              <Badge variant="default">Admin</Badge>
              <Badge variant="secondary">Member</Badge>
              <Badge variant="outline">Viewer</Badge>
              <Badge className="bg-billing">Billing</Badge>
            </div>
          </div>
        </div>
      </div>

      {/* Feedback */}
      <div id="feedback" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Feedback</h3>
        <div className="space-y-4 max-w-3xl">
          <Alert>
            <Info className="h-4 w-4" />
            <AlertTitle>Information</AlertTitle>
            <AlertDescription>
              This is an informational alert message.
            </AlertDescription>
          </Alert>
          <Alert variant="default" className="border-success text-success">
            <CheckCircle className="h-4 w-4" />
            <AlertTitle>Success</AlertTitle>
            <AlertDescription>
              Your operation completed successfully.
            </AlertDescription>
          </Alert>
          <Alert variant="default" className="border-warning text-warning-foreground bg-warning/10">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Warning</AlertTitle>
            <AlertDescription>
              Please review this important information.
            </AlertDescription>
          </Alert>
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>
              An error occurred while processing your request.
            </AlertDescription>
          </Alert>
        </div>
      </div>

      {/* States */}
      <div id="loading-states" className="space-y-6">
        <h3 className="text-2xl font-semibold text-foreground">Loading States</h3>
        <div className="space-y-4 max-w-3xl">
          <Card className="p-6">
            <div className="space-y-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-20 w-full" />
            </div>
          </Card>
          <Card className="p-6">
            <div className="flex items-center space-x-4">
              <Skeleton className="h-12 w-12 rounded-full" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-4 w-1/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            </div>
          </Card>
        </div>

        <div id="empty-state">
          <h3 className="text-2xl font-semibold text-foreground mt-8">Empty State</h3>
          <Card className="p-12 text-center max-w-2xl">
          <div className="mx-auto w-24 h-24 rounded-full bg-muted flex items-center justify-center mb-4">
            <Search className="h-12 w-12 text-muted-foreground" />
          </div>
          <h4 className="text-lg font-semibold text-foreground mb-2">No items found</h4>
          <p className="text-sm text-muted-foreground mb-6">
            Get started by creating your first item.
          </p>
          <Button>Create Item</Button>
        </Card>
      </div>

      {/* Responsive Note */}
      <div className="border-t border-border pt-8">
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Mobile Responsiveness</AlertTitle>
          <AlertDescription>
            Todos os componentes são projetados mobile-first e se adaptam automaticamente
            a diferentes tamanhos de tela. Teste redimensionando a janela do navegador.
          </AlertDescription>
        </Alert>
        </div>
      </div>
    </section>
  );
}
